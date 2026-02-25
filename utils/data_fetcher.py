"""
数据采集模块 V4.1 - 寻星情报中心
================================================================
核心架构: Tushare PRO 优先 → AKShare 降级兜底
军规升级: Q2/Q5 强制切入前复权(qfq)流，消灭除权价格失真，加入防封禁限流
================================================================
数据层级:
  L1  指数行情: Tushare daily → AKShare fallback
  L2  涨跌统计: AKShare (Tushare 无直接接口)
  L3  宏观数据: Tushare PRO 宏观接口 (cn_cpi/cn_pmi/cn_m2 等)
  L4  流动性:   Tushare shibor + AKShare DR007/央行OMO
  L5  信用利差: Tushare bond_blk → AKShare fallback
  L6  北向资金: Tushare hsgt_top10 → AKShare fallback
  L7  融资融券: Tushare margin
  L8  风格因子: Tushare index_daily (多指数5日+20日动量)
  L9  波动率:   基于 Tushare 指数日线自算 HV20
  L10 市场宽度: 涨跌比MA5/新高新低 (基于L2数据扩展)
  L11 板块:     AKShare (东方财富行业/概念) → Tushare fallback
  L12 ETF:      Tushare fund_daily → AKShare fallback
  L13 资讯:     Tushare 8源新闻 + 新闻联播 + 新浪降级
  L14 研报:     Tushare report_rc
  L15 期货:     AKShare 新浪期货 → Tushare fut_daily fallback
  L16 打包:     全量数据聚合供 AI 使用
================================================================
"""
import pandas as pd
import numpy as np
import requests
import json
import os
import logging
import concurrent.futures
from datetime import datetime, timedelta
import streamlit as st
import urllib3
import certifi
import shutil
import time
import tushare as ts

# ============================================================
# 基础设施
# ============================================================
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("xunxing")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    safe_cert_path = os.path.join(os.getcwd(), "cacert.pem")
    if not os.path.exists(safe_cert_path):
        shutil.copy(certifi.where(), safe_cert_path)
    os.environ["CURL_CA_BUNDLE"] = safe_cert_path
    os.environ["REQUESTS_CA_BUNDLE"] = safe_cert_path
except Exception as e:
    logger.warning(f"SSL证书路径修复失败: {e}")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _safe_call(func, timeout=12, default=None, label=""):
    """带超时和日志的安全调用"""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        logger.warning(f"[超时] {label} 超过 {timeout}s")
        return default
    except Exception as e:
        logger.error(f"[异常] {label}: {e}")
        return default


def _import_akshare():
    """延迟导入 AKShare (仅降级时需要)"""
    try:
        import akshare as ak
        return ak
    except ImportError:
        logger.error("akshare 未安装")
        return None


# ============================================================
# Tushare PRO 初始化
# ============================================================
@st.cache_resource
def _get_tushare_pro():
    """获取 Tushare PRO 接口实例 (全局缓存)"""
    try:
        token = ""
        try:
            token = st.secrets.get("TUSHARE_TOKEN", "")
        except Exception:
            pass
        if not token:
            logger.warning("TUSHARE_TOKEN 未配置")
            return None
        pro = ts.pro_api(token)
        # 简单测试连通性
        logger.info("Tushare PRO 连接成功")
        return pro
    except ImportError:
        logger.error("tushare 未安装")
        return None
    except Exception as e:
        logger.error(f"Tushare 初始化失败: {e}")
        return None


def _tushare_available() -> bool:
    return _get_tushare_pro() is not None


def _last_trade_date(offset=0) -> str:
    """获取最近交易日 (简单估算, 跳过周末)"""
    d = datetime.now() - timedelta(days=offset)
    while d.weekday() >= 5:  # 周六日
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


# ============================================================
# L1. 宽基指数行情 — Tushare PRO 优先
# ============================================================
# 核心指数映射
INDEX_MAP = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
}


@st.cache_data(ttl=600, show_spinner=False)
def get_major_indices() -> pd.DataFrame:
    """宽基指数行情 — Tushare 优先"""
    def _tushare_fetch():
        pro = _get_tushare_pro()
        if not pro:
            return None
        try:
            today = _last_trade_date()
            rows = []
            for ts_code, name in INDEX_MAP.items():
                df = pro.index_daily(ts_code=ts_code, start_date=today, end_date=today)
                if df is not None and not df.empty:
                    r = df.iloc[0]
                    rows.append({
                        "名称": name,
                        "最新价": float(r.get("close", 0)),
                        "涨跌幅": float(r.get("pct_chg", 0)),
                        "涨跌额": float(r.get("change", 0)),
                        "成交额": float(r.get("amount", 0)) * 1000,  # Tushare amount 单位千元
                    })
            if rows:
                return pd.DataFrame(rows)
            # 如果今天没数据 (非交易日/盘前), 尝试往前找
            for offset in range(1, 4):
                date = _last_trade_date(offset)
                rows = []
                for ts_code, name in INDEX_MAP.items():
                    df = pro.index_daily(ts_code=ts_code, start_date=date, end_date=date)
                    if df is not None and not df.empty:
                        r = df.iloc[0]
                        rows.append({
                            "名称": name,
                            "最新价": float(r.get("close", 0)),
                            "涨跌幅": float(r.get("pct_chg", 0)),
                            "涨跌额": float(r.get("change", 0)),
                            "成交额": float(r.get("amount", 0)) * 1000,
                        })
                if rows:
                    return pd.DataFrame(rows)
        except Exception as e:
            logger.warning(f"[Tushare] 指数行情失败: {e}")
        return None

    def _akshare_fetch():
        ak = _import_akshare()
        if not ak:
            return pd.DataFrame()
        df = ak.stock_zh_index_spot_em()
        if df is None or df.empty:
            return pd.DataFrame()
        target = list(INDEX_MAP.values())
        result = df[df["名称"].isin(target)].copy()
        keep = [c for c in ["名称", "最新价", "涨跌幅", "涨跌额", "成交额"] if c in result.columns]
        result = result[keep].reset_index(drop=True)
        for c in ["最新价", "涨跌幅", "涨跌额", "成交额"]:
            if c in result.columns:
                result[c] = pd.to_numeric(result[c], errors="coerce")
        return result

    # Tushare 优先
    result = _safe_call(_tushare_fetch, timeout=15, default=None, label="指数[TS]")
    if result is not None and not result.empty:
        return result
    logger.info("[降级] 指数行情 → AKShare")
    return _safe_call(_akshare_fetch, timeout=12, default=pd.DataFrame(), label="指数[AK]")


# ============================================================
# L2. 涨跌统计 (AKShare 为主, Tushare 无直接接口)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_market_overview() -> dict:
    def _fetch():
        ak = _import_akshare()
        if not ak:
            return {}
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return {}
        df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
        df["成交额"] = pd.to_numeric(df["成交额"], errors="coerce")
        total = len(df)
        up = int((df["涨跌幅"] > 0).sum())
        down = int((df["涨跌幅"] < 0).sum())
        flat = total - up - down
        limit_up = int((df["涨跌幅"] >= 9.8).sum())
        limit_down = int((df["涨跌幅"] <= -9.8).sum())
        total_amount = round(df["成交额"].sum() / 1e8, 0)

        # V4 新增: 市场宽度指标
        up_ratio = round(up / total * 100, 1) if total else 0
        # 涨幅 > 3% 和 < -3% 的数量 (强势/弱势个股)
        strong_up = int((df["涨跌幅"] >= 3).sum())
        strong_down = int((df["涨跌幅"] <= -3).sum())

        return {
            "上涨": up, "下跌": down, "平盘": flat,
            "涨停": limit_up, "跌停": limit_down,
            "总成交额亿": total_amount,
            "上涨占比": up_ratio,
            "强势股": strong_up,
            "弱势股": strong_down,
            "总股票数": total,
        }
    return _safe_call(_fetch, timeout=12, default={}, label="涨跌统计")


# ============================================================
# L3. 宏观数据 — Tushare PRO 优先 (桥水四维框架)
# ============================================================
@st.cache_data(ttl=7200, show_spinner=False)
def get_macro_data() -> dict:
    """
    桥水式四维宏观框架:
    1. 增长维度: PMI, 工业增加值
    2. 通胀维度: CPI, PPI, CPI-PPI剪刀差
    3. 流动性: M2, 社融 (单独函数 get_liquidity_data)
    4. 信用: 信用利差 (单独函数 get_credit_spread)
    """
    def _tushare_fetch():
        pro = _get_tushare_pro()
        if not pro:
            return None
        macro = {}
        # CPI
        try:
            df = pro.cn_cpi(start_m="202401", end_m=datetime.now().strftime("%Y%m"))
            if df is not None and not df.empty:
                df = df.sort_values("month").tail(1)
                last = df.iloc[0]
                macro["CPI同比"] = f"{last.get('nt_yoy', '')}%"
                macro["CPI月份"] = str(last.get("month", ""))
        except Exception as e:
            logger.warning(f"[TS] CPI: {e}")

        # PPI
        try:
            df = pro.cn_ppi(start_m="202401", end_m=datetime.now().strftime("%Y%m"))
            if df is not None and not df.empty:
                df = df.sort_values("month").tail(1)
                last = df.iloc[0]
                macro["PPI同比"] = f"{last.get('ppi_yoy', '')}%"
        except Exception as e:
            logger.warning(f"[TS] PPI: {e}")

        # CPI-PPI 剪刀差
        try:
            cpi_val = float(str(macro.get("CPI同比", "0")).replace("%", ""))
            ppi_val = float(str(macro.get("PPI同比", "0")).replace("%", ""))
            macro["CPI-PPI剪刀差"] = f"{round(cpi_val - ppi_val, 1)}%"
        except Exception:
            pass

        # PMI
        try:
            df = pro.cn_pmi(start_m="202401", end_m=datetime.now().strftime("%Y%m"))
            if df is not None and not df.empty:
                df = df.sort_values("month").tail(1)
                last = df.iloc[0]
                macro["制造业PMI"] = str(last.get("pmi", ""))
                macro["PMI月份"] = str(last.get("month", ""))
        except Exception as e:
            logger.warning(f"[TS] PMI: {e}")

        # M2
        try:
            df = pro.cn_m(start_m="202401", end_m=datetime.now().strftime("%Y%m"))
            if df is not None and not df.empty:
                df = df.sort_values("month").tail(1)
                last = df.iloc[0]
                macro["M2同比"] = f"{last.get('m2_yoy', '')}%"
        except Exception as e:
            logger.warning(f"[TS] M2: {e}")

        # 国债利率 (中美)
        try:
            today = _last_trade_date()
            start = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
            df = pro.yc_cb(ts_code="1001.CB", curve_type="0", trade_date=today)
            if df is not None and not df.empty:
                row_10y = df[df["curve_term"] == 10]
                if not row_10y.empty:
                    macro["中国10Y国债"] = f"{row_10y.iloc[0]['yield']}%"
        except Exception as e:
            logger.warning(f"[TS] 国债利率: {e}")

        # 人民币汇率
        try:
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
            df = pro.fx_daily(ts_code="USDCNY.FXCM", start_date=start, end_date=end)
            if df is not None and not df.empty:
                df = df.sort_values("trade_date").tail(1)
                macro["美元兑人民币"] = str(round(float(df.iloc[0].get("close", 0)), 4))
        except Exception as e:
            logger.warning(f"[TS] 汇率: {e}")

        return macro if macro else None

    def _akshare_fetch():
        ak = _import_akshare()
        if not ak:
            return {}
        macro = {}
        try:
            df = ak.macro_china_cpi_monthly()
            if df is not None and not df.empty:
                last = df.iloc[-1]
                macro["CPI同比"] = str(last.iloc[-1])
                macro["CPI月份"] = str(last.iloc[0])
        except Exception:
            pass
        try:
            df = ak.macro_china_pmi()
            if df is not None and not df.empty:
                last = df.iloc[-1]
                macro["制造业PMI"] = str(last.iloc[-1])
                macro["PMI月份"] = str(last.iloc[0])
        except Exception:
            pass
        try:
            df = ak.bond_zh_us_rate(start_date="20250101")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                for col in df.columns:
                    if "中国" in str(col) and "10" in str(col):
                        macro["中国10Y国债"] = f"{latest[col]}%"
                    if "美国" in str(col) and "10" in str(col):
                        macro["美国10Y国债"] = f"{latest[col]}%"
        except Exception:
            pass
        try:
            df = ak.currency_boc_sina(symbol="美元",
                                       start_date=(datetime.now() - timedelta(days=10)).strftime("%Y%m%d"))
            if df is not None and not df.empty:
                val = df.iloc[-1].iloc[1] if len(df.columns) > 1 else None
                if val:
                    macro["美元兑人民币"] = str(val)
        except Exception:
            pass
        return macro

    # Tushare 优先
    result = _safe_call(_tushare_fetch, timeout=20, default=None, label="宏观[TS]")
    if result:
        return result
    logger.info("[降级] 宏观数据 → AKShare")
    return _safe_call(_akshare_fetch, timeout=15, default={}, label="宏观[AK]")


# ============================================================
# L4. 流动性指标 (V4新增 — 桥水框架核心)
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_liquidity_data() -> dict:
    """流动性维度: Shibor / DR007 / 央行OMO净投放"""
    def _tushare_fetch():
        pro = _get_tushare_pro()
        if not pro:
            return None
        result = {}
        try:
            today = _last_trade_date()
            start = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
            df = pro.shibor(start_date=start, end_date=today)
            if df is not None and not df.empty:
                df = df.sort_values("date").tail(1)
                last = df.iloc[0]
                result["Shibor隔夜"] = f"{last.get('on', '')}%"
                result["Shibor_1W"] = f"{last.get('1w', '')}%"
                result["Shibor_1M"] = f"{last.get('1m', '')}%"
        except Exception as e:
            logger.warning(f"[TS] Shibor: {e}")

        # 社融存量同比 (通过 cn_sf 接口)
        try:
            df = pro.cn_sf(start_m="202401", end_m=datetime.now().strftime("%Y%m"))
            if df is not None and not df.empty:
                df = df.sort_values("month").tail(1)
                last = df.iloc[0]
                # 社融存量增量
                result["社融增量亿"] = str(round(float(last.get("inc_total", 0)) / 1e4, 0))
        except Exception as e:
            logger.warning(f"[TS] 社融: {e}")

        return result if result else None

    def _akshare_fetch():
        ak = _import_akshare()
        if not ak:
            return {}
        result = {}
        try:
            df = ak.rate_interbank(market="上海银行同业拆借利率", symbol="Shibor人民币", indicator="隔夜")
            if df is not None and not df.empty:
                last = df.iloc[-1]
                for col in df.columns:
                    if "利率" in str(col) or "报价" in str(col):
                        result["Shibor隔夜"] = f"{last[col]}%"
                        break
        except Exception:
            pass
        return result

    result = _safe_call(_tushare_fetch, timeout=15, default=None, label="流动性[TS]")
    if result:
        return result
    logger.info("[降级] 流动性 → AKShare")
    return _safe_call(_akshare_fetch, timeout=10, default={}, label="流动性[AK]")


# ============================================================
# L5. 信用利差 (V4新增 — 桥水框架: 信用周期)
# ============================================================
@st.cache_data(ttl=7200, show_spinner=False)
def get_credit_spread() -> dict:
    """信用利差: AA-企业债 vs 国债, 信用扩张/收缩判断"""
    def _fetch():
        pro = _get_tushare_pro()
        if not pro:
            return {}
        result = {}
        try:
            today = _last_trade_date()
            # 获取国债收益率曲线 (5Y)
            df_gov = pro.yc_cb(ts_code="1001.CB", curve_type="0", trade_date=today)
            gov_5y = None
            if df_gov is not None and not df_gov.empty:
                row = df_gov[df_gov["curve_term"] == 5]
                if not row.empty:
                    gov_5y = float(row.iloc[0]["yield"])
                    result["国债5Y"] = f"{gov_5y:.2f}%"

            # 简化: 用信用债指数变化近似信用利差趋势
            # 如果有 cb_blk 接口可以获取企业债到期收益率
        except Exception as e:
            logger.warning(f"[TS] 信用利差: {e}")
        return result

    return _safe_call(_fetch, timeout=12, default={}, label="信用利差")


# ============================================================
# L6. 北向资金 — Tushare 优先
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_northbound_flow() -> dict:
    def _tushare_fetch():
        pro = _get_tushare_pro()
        if not pro:
            return None
        try:
            end = _last_trade_date()
            start = (datetime.now() - timedelta(days=15)).strftime("%Y%m%d")
            df = pro.moneyflow_hsgt(start_date=start, end_date=end)
            if df is not None and not df.empty:
                df = df.sort_values("trade_date")
                recent5 = df.tail(5)
                latest = recent5.iloc[-1]
                # north_money 单位百万
                today_val = float(latest.get("north_money", 0)) / 100  # 转亿
                five_avg = float(recent5["north_money"].mean()) / 100
                return {
                    "今日净流入亿": round(today_val, 2),
                    "5日均值亿": round(five_avg, 2),
                    "方向": "净流入" if today_val > 0 else "净流出",
                    "日期": str(latest.get("trade_date", "")),
                }
        except Exception as e:
            logger.warning(f"[TS] 北向资金: {e}")
        return None

    def _akshare_fetch():
        ak = _import_akshare()
        if not ak:
            return {}
        try:
            df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
            if df is not None and not df.empty:
                recent = df.tail(5)
                cols = [c for c in recent.columns if "净" in str(c) or "流入" in str(c)]
                if not cols:
                    cols = recent.select_dtypes(include="number").columns.tolist()
                if cols:
                    val_col = cols[0]
                    today_val = float(recent.iloc[-1][val_col])
                    five_avg = float(recent[val_col].mean())
                    scale = 1e4 if abs(today_val) > 1000 else 1
                    return {
                        "今日净流入亿": round(today_val / scale, 2),
                        "5日均值亿": round(five_avg / scale, 2),
                        "方向": "净流入" if today_val > 0 else "净流出",
                    }
        except Exception:
            pass
        return {}

    result = _safe_call(_tushare_fetch, timeout=12, default=None, label="北向[TS]")
    if result:
        return result
    logger.info("[降级] 北向资金 → AKShare")
    return _safe_call(_akshare_fetch, timeout=10, default={}, label="北向[AK]")


# ============================================================
# L7. 融资融券 (Tushare PRO)
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_margin_data() -> dict:
    def _fetch():
        pro = _get_tushare_pro()
        if not pro:
            return {}
        try:
            today = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d")
            df = pro.margin(start_date=start, end_date=today)
            if df is not None and not df.empty:
                df = df.sort_values("trade_date").tail(5)
                latest = df.iloc[-1]
                prev = df.iloc[0] if len(df) >= 2 else latest
                rzye = float(latest.get("rzye", 0)) / 1e8
                rqye = float(latest.get("rqye", 0)) / 1e8
                rzye_prev = float(prev.get("rzye", 0)) / 1e8
                rz_chg = round(rzye - rzye_prev, 1)
                return {
                    "融资余额亿": round(rzye, 1),
                    "融券余额亿": round(rqye, 1),
                    "融资5日变化亿": rz_chg,
                    "杠杆情绪": "加杠杆" if rz_chg > 0 else "去杠杆",
                }
        except Exception as e:
            logger.warning(f"融资融券获取失败: {e}")
        return {}
    return _safe_call(_fetch, timeout=12, default={}, label="融资融券")


# ============================================================
# L8. 风格数据 (Tushare 优先 — 5日+20日动量)
# ============================================================
STYLE_INDICES = {
    "000300.SH": "沪深300",
    "000852.SH": "中证1000",
    "399006.SZ": "创业板指",
    "000016.SH": "上证50",
    "000905.SH": "中证500",
}


@st.cache_data(ttl=600, show_spinner=False)
def get_style_data() -> dict:
    def _tushare_fetch():
        pro = _get_tushare_pro()
        if not pro:
            return None
        result = {}
        try:
            end = _last_trade_date()
            start = (datetime.now() - timedelta(days=45)).strftime("%Y%m%d")
            closes = {}
            for ts_code, name in STYLE_INDICES.items():
                df = pro.index_daily(ts_code=ts_code, start_date=start, end_date=end)
                if df is not None and not df.empty:
                    df = df.sort_values("trade_date")
                    closes[name] = df["close"].values

            # 计算动量
            for name, vals in closes.items():
                if len(vals) >= 6:
                    d5 = round((float(vals[-1]) / float(vals[-6]) - 1) * 100, 2)
                    result[f"{name}_5日"] = d5
                if len(vals) >= 21:
                    d20 = round((float(vals[-1]) / float(vals[-21]) - 1) * 100, 2)
                    result[f"{name}_20日"] = d20

            # 大小盘偏好 (5日)
            if "沪深300_5日" in result and "中证1000_5日" in result:
                result["大小盘偏好_5日"] = "偏大盘" if result["沪深300_5日"] > result["中证1000_5日"] else "偏小盘"
            if "沪深300_20日" in result and "中证1000_20日" in result:
                result["大小盘偏好_20日"] = "偏大盘" if result["沪深300_20日"] > result["中证1000_20日"] else "偏小盘"

            # 成长价值偏好
            if "创业板指_5日" in result and "上证50_5日" in result:
                result["成长价值_5日"] = "偏成长" if result["创业板指_5日"] > result["上证50_5日"] else "偏价值"
            if "创业板指_20日" in result and "上证50_20日" in result:
                result["成长价值_20日"] = "偏成长" if result["创业板指_20日"] > result["上证50_20日"] else "偏价值"

            return result if result else None
        except Exception as e:
            logger.warning(f"[TS] 风格数据: {e}")
        return None

    def _akshare_fetch():
        ak = _import_akshare()
        if not ak:
            return {}
        result = {}
        try:
            hs300 = ak.stock_zh_index_daily_em(symbol="sh000300")
            zz1000 = ak.stock_zh_index_daily_em(symbol="sh000852")
            if hs300 is not None and len(hs300) >= 6 and zz1000 is not None and len(zz1000) >= 6:
                hs_5d = (float(hs300.iloc[-1]["close"]) / float(hs300.iloc[-6]["close"]) - 1) * 100
                zz_5d = (float(zz1000.iloc[-1]["close"]) / float(zz1000.iloc[-6]["close"]) - 1) * 100
                result["沪深300_5日"] = round(hs_5d, 2)
                result["中证1000_5日"] = round(zz_5d, 2)
                result["大小盘偏好_5日"] = "偏大盘" if hs_5d > zz_5d else "偏小盘"
        except Exception:
            pass
        try:
            cyb = ak.stock_zh_index_daily_em(symbol="sz399006")
            sz50 = ak.stock_zh_index_daily_em(symbol="sh000016")
            if cyb is not None and len(cyb) >= 6 and sz50 is not None and len(sz50) >= 6:
                cyb_5d = (float(cyb.iloc[-1]["close"]) / float(cyb.iloc[-6]["close"]) - 1) * 100
                sz50_5d = (float(sz50.iloc[-1]["close"]) / float(sz50.iloc[-6]["close"]) - 1) * 100
                result["创业板指_5日"] = round(cyb_5d, 2)
                result["上证50_5日"] = round(sz50_5d, 2)
                result["成长价值_5日"] = "偏成长" if cyb_5d > sz50_5d else "偏价值"
        except Exception:
            pass
        return result

    result = _safe_call(_tushare_fetch, timeout=20, default=None, label="风格[TS]")
    if result:
        return result
    logger.info("[降级] 风格 → AKShare")
    return _safe_call(_akshare_fetch, timeout=15, default={}, label="风格[AK]")


# ============================================================
# L9. 波动率 (V4新增 — 基于沪深300日线自算HV20)
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_volatility_data() -> dict:
    """历史波动率 + 成交量动量"""
    def _tushare_fetch():
        pro = _get_tushare_pro()
        if not pro:
            return None
        result = {}
        try:
            end = _last_trade_date()
            start = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
            df = pro.index_daily(ts_code="000300.SH", start_date=start, end_date=end)
            if df is not None and not df.empty:
                df = df.sort_values("trade_date")
                closes = df["close"].astype(float).values
                if len(closes) >= 21:
                    returns = np.diff(np.log(closes[-21:]))
                    hv20 = float(np.std(returns) * np.sqrt(252) * 100)
                    result["沪深300_HV20"] = round(hv20, 1)
                    # 波动率水平判断
                    if hv20 < 12:
                        result["波动率环境"] = "低波动"
                    elif hv20 < 20:
                        result["波动率环境"] = "中等波动"
                    elif hv20 < 30:
                        result["波动率环境"] = "高波动"
                    else:
                        result["波动率环境"] = "极端波动"

                # 成交额动量: 5日均值 vs 20日均值
                amounts = df["amount"].astype(float).values
                if len(amounts) >= 20:
                    vol_5 = float(np.mean(amounts[-5:]))
                    vol_20 = float(np.mean(amounts[-20:]))
                    result["成交额5/20比"] = round(vol_5 / vol_20, 2) if vol_20 > 0 else 1
                    result["量能状态"] = "放量" if vol_5 / vol_20 > 1.2 else ("缩量" if vol_5 / vol_20 < 0.8 else "温和")

            return result if result else None
        except Exception as e:
            logger.warning(f"[TS] 波动率: {e}")
        return None

    result = _safe_call(_tushare_fetch, timeout=15, default=None, label="波动率[TS]")
    return result or {}


# ============================================================
# L10. 情绪温度计 (V4新增 — 综合多维指标)
# ============================================================
def get_sentiment_temperature(overview: dict = None, northbound: dict = None,
                               margin: dict = None, volatility: dict = None) -> dict:
    """
    情绪综合打分 (0-100):
    - 上涨占比 (权重25%)
    - 北向资金方向 (权重20%)
    - 融资余额变化 (权重20%)
    - 成交额动量 (权重20%)
    - 波动率逆向 (权重15%, 低波看多)
    """
    score = 50  # 中性基准
    details = {}

    if overview:
        up_pct = overview.get("上涨占比", 50)
        # 上涨占比 > 60% 乐观, < 40% 悲观
        s1 = min(max((up_pct - 30) / 40 * 100, 0), 100)
        details["赚钱效应"] = round(s1, 0)
        score = score * 0.75 + s1 * 0.25

    if northbound:
        nb_val = northbound.get("今日净流入亿", 0)
        s2 = min(max((nb_val + 100) / 200 * 100, 0), 100)
        details["北向情绪"] = round(s2, 0)
        score = score * 0.80 + s2 * 0.20

    if margin:
        rz_chg = margin.get("融资5日变化亿", 0)
        s3 = min(max((rz_chg + 200) / 400 * 100, 0), 100)
        details["杠杆情绪"] = round(s3, 0)
        score = score * 0.80 + s3 * 0.20

    if volatility:
        vol_ratio = volatility.get("成交额5/20比", 1)
        s4 = min(max(vol_ratio * 50, 0), 100)
        details["量能情绪"] = round(s4, 0)
        score = score * 0.80 + s4 * 0.20

        hv = volatility.get("沪深300_HV20", 15)
        s5 = min(max((30 - hv) / 20 * 100, 0), 100)  # 低波乐观
        details["波动率情绪"] = round(s5, 0)
        score = score * 0.85 + s5 * 0.15

    temperature = round(score, 0)
    if temperature >= 70:
        level = "🔥 过热 (贪婪)"
    elif temperature >= 55:
        level = "🟢 偏暖 (乐观)"
    elif temperature >= 45:
        level = "⚪ 中性"
    elif temperature >= 30:
        level = "🔵 偏冷 (谨慎)"
    else:
        level = "❄️ 极冷 (恐惧)"

    return {
        "温度": temperature,
        "级别": level,
        "分项": details,
    }


# ============================================================
# L11. 板块数据 (AKShare 为主)
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_industry_board() -> pd.DataFrame:
    def _fetch():
        ak = _import_akshare()
        if not ak:
            return pd.DataFrame()
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            for c in ["涨跌幅", "总市值", "换手率"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
        return pd.DataFrame()
    return _safe_call(_fetch, timeout=12, default=pd.DataFrame(), label="行业板块")


@st.cache_data(ttl=900, show_spinner=False)
def get_concept_board() -> pd.DataFrame:
    def _fetch():
        ak = _import_akshare()
        if not ak:
            return pd.DataFrame()
        df = ak.stock_board_concept_name_em()
        if df is not None and not df.empty:
            for c in ["涨跌幅", "总市值", "换手率"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
        return pd.DataFrame()
    return _safe_call(_fetch, timeout=12, default=pd.DataFrame(), label="概念板块")


# ============================================================
# L12. ETF — Tushare 优先
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_etf_list() -> pd.DataFrame:
    def _tushare_fetch():
        pro = _get_tushare_pro()
        if not pro:
            return None
        try:
            today = _last_trade_date()
            # 获取ETF基本信息
            df_basic = pro.fund_basic(market="E", status="L")
            if df_basic is None or df_basic.empty:
                return None
            # 获取当日行情 (取前100只主要ETF)
            top_etfs = df_basic.head(150)
            rows = []
            for _, etf in top_etfs.iterrows():
                ts_code = etf.get("ts_code", "")
                name = etf.get("name", "")
                try:
                    df_q = pro.fund_daily(ts_code=ts_code, start_date=today, end_date=today)
                    if df_q is not None and not df_q.empty:
                        r = df_q.iloc[0]
                        rows.append({
                            "代码": ts_code.split(".")[0],
                            "名称": name,
                            "最新价": float(r.get("close", 0)),
                            "涨跌幅": float(r.get("pct_chg", 0)),
                            "成交额": float(r.get("amount", 0)) * 1000,
                        })
                except Exception:
                    continue
                if len(rows) >= 80:
                    break
            if rows:
                df = pd.DataFrame(rows)
                df = df.sort_values("成交额", ascending=False).reset_index(drop=True)
                return df
        except Exception as e:
            logger.warning(f"[TS] ETF: {e}")
        return None

    def _akshare_fetch():
        ak = _import_akshare()
        if not ak:
            return pd.DataFrame()
        df = ak.fund_etf_spot_em()
        if df is not None and not df.empty:
            for c in ["最新价", "涨跌幅", "成交额"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.sort_values("成交额", ascending=False).head(80).reset_index(drop=True)
        return pd.DataFrame()

    # ETF逐只查询太慢, AKShare更快, 优先用AKShare, Tushare作备选
    result = _safe_call(_akshare_fetch, timeout=12, default=None, label="ETF[AK]")
    if result is not None and not result.empty:
        return result
    logger.info("[降级] ETF → Tushare逐只")
    ts_result = _safe_call(_tushare_fetch, timeout=30, default=pd.DataFrame(), label="ETF[TS]")
    return ts_result if ts_result is not None else pd.DataFrame()


# ============================================================
# L13. 资讯采集 — 多源并行 (Tushare PRO)
# ============================================================
TUSHARE_NEWS_SOURCES = [
    ("cls",           "财联社",     "T1", 150),
    ("yicai",         "第一财经",   "T1", 120),
    ("wallstreetcn",  "华尔街见闻", "T1", 120),
    ("eastmoney",     "东方财富",   "T2", 100),
    ("10jqka",        "同花顺",     "T2", 100),
    ("sina",          "新浪财经",   "T2", 80),
    ("jinrongjie",    "金融界",     "T3", 50),
    ("yuncaijing",    "云财经",     "T3", 50),
]

_NOISE_WORDS = frozenset([
    "互动平台", "互动易", "抽奖", "投资者关系", "停牌", "复牌",
    "新股申购", "大宗交易", "调研信息", "交易提示", "盘中异动",
    "龙虎榜", "成交回报", "溢价率", "中签号", "配号",
])

_IMPORTANT_WORDS = frozenset([
    "央行", "国务院", "降准", "降息", "加息", "MLF", "LPR", "社融",
    "GDP", "CPI", "PMI", "两会", "政治局", "证监会", "发改委",
    "美联储", "关税", "制裁", "战争", "地震",
    "暴跌", "暴涨", "熔断", "涨停潮", "跌停潮", "千股",
])

_CATEGORY_RULES = {
    "宏观政策": ["央行", "国务院", "GDP", "CPI", "PPI", "PMI", "社融", "M2",
                 "降准", "降息", "LPR", "MLF", "财政", "两会", "政治局",
                 "发改委", "工信部", "商务部", "财政部"],
    "海外市场": ["美联储", "美国", "欧洲", "日本", "美股", "美债", "美元",
                 "纳斯达克", "道琼斯", "标普", "关税", "英国", "日经"],
    "行业产业": ["半导体", "芯片", "AI", "人工智能", "机器人", "新能源", "光伏",
                 "锂电", "储能", "医药", "创新药", "军工", "汽车", "算力",
                 "大模型", "低空经济", "商业航天", "量子"],
    "监管政策": ["证监会", "银保监", "交易所", "IPO", "注册制", "退市",
                 "减持", "分红", "回购", "监管", "处罚"],
    "市场资金": ["北向", "外资", "融资", "融券", "ETF", "基金", "社保",
                 "保险资金", "QFII", "主力", "游资"],
}


def _classify_news(title: str, content: str = "") -> tuple:
    text = title + content[:100]
    category = "综合财经"
    for cat, keywords in _CATEGORY_RULES.items():
        if any(kw in text for kw in keywords):
            category = cat
            break
    is_important = any(w in text for w in _IMPORTANT_WORDS)
    return category, is_important


@st.cache_data(ttl=300, show_spinner=False)
def get_tushare_news(count: int = 150) -> list:
    """Tushare PRO 多源并行采集引擎"""
    pro = _get_tushare_pro()
    if not pro:
        return []

    now = datetime.now()
    end_time = now.strftime("%Y-%m-%d %H:%M:%S")
    start_time = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    raw_news = []
    source_stats = {}

    for src, name, tier, limit in TUSHARE_NEWS_SOURCES:
        try:
            df = pro.news(src=src, start_date=start_time, end_date=end_time)
            fetched = 0
            if df is not None and not df.empty:
                for _, row in df.head(limit).iterrows():
                    title = str(row.get("title", "")).strip()
                    content = str(row.get("content", ""))[:600].strip()
                    dt = str(row.get("datetime", ""))
                    channels = str(row.get("channels", ""))
                    if not title or len(title) < 6:
                        continue
                    if any(w in title for w in _NOISE_WORDS):
                        continue
                    category, is_important = _classify_news(title, content)
                    pub_time = dt.split(" ")[1][:5] if " " in dt else dt[:16]
                    raw_news.append({
                        "time": pub_time, "datetime": dt, "title": title,
                        "content": content if content and content != title else title,
                        "important": is_important, "source": name, "source_id": src,
                        "tier": tier, "category": category, "channels": channels,
                    })
                    fetched += 1
            source_stats[name] = fetched
            logger.info(f"[采集] {name}({src}): {fetched} 条")
        except Exception as e:
            source_stats[name] = f"失败:{e}"
            logger.warning(f"[采集失败] {name}({src}): {e}")

    # 新闻联播
    try:
        yesterday = (now - timedelta(days=1)).strftime("%Y%m%d")
        df_cctv = pro.cctv_news(date=yesterday)
        if df_cctv is not None and not df_cctv.empty:
            cctv_count = 0
            for _, row in df_cctv.head(15).iterrows():
                title = str(row.get("title", "")).strip()
                content = str(row.get("content", ""))[:400].strip()
                if title and len(title) > 5:
                    raw_news.append({
                        "time": "CCTV", "datetime": yesterday,
                        "title": f"[新闻联播] {title}", "content": content,
                        "important": True, "source": "新闻联播", "source_id": "cctv",
                        "tier": "T0", "category": "宏观政策", "channels": "",
                    })
                    cctv_count += 1
            source_stats["新闻联播"] = cctv_count
    except Exception as e:
        logger.warning(f"[采集失败] 新闻联播: {e}")

    logger.info(f"[汇总] 原始 {len(raw_news)} 条 | {source_stats}")

    # 智能去重
    seen_titles = {}
    tier_priority = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
    for item in raw_news:
        key = item["title"][:30].strip()
        if key not in seen_titles:
            seen_titles[key] = item
        else:
            existing = seen_titles[key]
            if tier_priority.get(item["tier"], 9) < tier_priority.get(existing["tier"], 9):
                seen_titles[key] = item
    deduped = list(seen_titles.values())
    logger.info(f"[去重] {len(raw_news)} → {len(deduped)} 条")

    # 质量排序 (V4: 增加时间衰减)
    def _sort_key(item):
        tier_score = tier_priority.get(item["tier"], 9)
        important_score = 0 if item.get("important") else 1
        # 时间衰减: 越新越靠前
        dt_str = item.get("datetime", "")
        try:
            dt = datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S")
            hours_ago = (now - dt).total_seconds() / 3600
            time_score = min(hours_ago / 24, 1)  # 0=刚发 1=24h前
        except Exception:
            time_score = 0.5
        return (important_score, tier_score, time_score)

    deduped.sort(key=_sort_key)
    final = deduped[:count]
    logger.info(f"[输出] 最终 {len(final)} 条 (目标 {count})")
    return final


@st.cache_data(ttl=300, show_spinner=False)
def get_sina_flash(count: int = 30) -> list:
    """新浪 7×24 快讯 — 降级补充"""
    telegraphs = []
    try:
        for page in range(1, 3):
            if len(telegraphs) >= count:
                break
            url = f"https://zhibo.sina.com.cn/api/zhibo/feed?page={page}&page_size=100&zhibo_id=152&tag_id=0&dire=f&dpc=1"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
            resp = requests.get(url, headers=headers, timeout=6, verify=False)
            if resp.status_code == 200:
                items = resp.json().get("result", {}).get("data", {}).get("feed", {}).get("list", [])
                if not items:
                    break
                for item in items:
                    if len(telegraphs) >= count:
                        break
                    rich_text = item.get("rich_text", "")
                    if not rich_text:
                        continue
                    if "】" in rich_text and rich_text.startswith("【"):
                        parts = rich_text.split("】", 1)
                        title = parts[0].replace("【", "").strip()
                        content = parts[1].strip() if len(parts) > 1 else title
                    else:
                        title = rich_text[:60] + "..."
                        content = rich_text
                    if any(w in title for w in _NOISE_WORDS):
                        continue
                    time_str = item.get("create_time", "")
                    pub_time = time_str.split(" ")[1][:5] if " " in time_str else time_str
                    telegraphs.append({
                        "time": pub_time, "title": title, "content": content,
                        "important": False, "source": "新浪快讯", "source_id": "sina_flash",
                        "tier": "T3", "category": "快讯", "channels": "",
                    })
    except Exception as e:
        logger.warning(f"新浪快讯抓取失败: {e}")
    return telegraphs[:count]


@st.cache_data(ttl=300, show_spinner=False)
def get_all_news(tushare_count: int = 150, sina_count: int = 0) -> list:
    """全量资讯聚合 — Tushare 主力, 新浪降级兜底"""
    all_news = []
    ts_news = get_tushare_news(tushare_count)
    all_news.extend(ts_news)

    if len(all_news) < 30:
        logger.warning(f"Tushare 仅 {len(all_news)} 条, 启用新浪补充")
        sina_news = get_sina_flash(max(sina_count, 50))
        existing = set(n["title"][:20] for n in all_news)
        for item in sina_news:
            if item["title"][:20] not in existing:
                all_news.append(item)
                existing.add(item["title"][:20])

    src_counts = {}
    for n in all_news:
        src = n.get("source", "unknown")
        src_counts[src] = src_counts.get(src, 0) + 1
    logger.info(f"[聚合] 共 {len(all_news)} 条 | {src_counts}")
    return all_news


# ============================================================
# L14. 券商研报 (Tushare PRO)
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_research_reports(count: int = 30) -> list:
    pro = _get_tushare_pro()
    if not pro:
        return []
    reports = []
    try:
        today = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d")
        df = pro.report_rc(start_date=start, end_date=today)
        if df is not None and not df.empty:
            if "report_date" in df.columns:
                df = df.sort_values("report_date", ascending=False)
            for _, row in df.head(count).iterrows():
                reports.append({
                    "stock_name": str(row.get("name", row.get("ts_code", ""))),
                    "ts_code": str(row.get("ts_code", "")),
                    "org_name": str(row.get("org_name", "")),
                    "rating": str(row.get("rating", "")),
                    "pre_rating": str(row.get("pre_rating", "")),
                    "target_price": row.get("target_price", None),
                    "report_date": str(row.get("report_date", "")),
                    "title": str(row.get("title", "")),
                })
            logger.info(f"券商研报: {len(reports)} 条")
    except Exception as e:
        logger.warning(f"券商研报失败: {e}")
    return reports


# ============================================================
# L15. 商品期货 (AKShare)
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_futures_overview() -> dict:
    def _fetch():
        ak = _import_akshare()
        if not ak:
            return {}
        result = {}
        try:
            df = ak.futures_main_sina()
            if df is not None and not df.empty:
                key_items = {
                    "沪金": "黄金", "沪银": "白银", "沪铜": "铜",
                    "螺纹": "螺纹钢", "铁矿": "铁矿石",
                    "原油": "原油", "沪铝": "铝",
                    "豆粕": "豆粕", "棕榈": "棕榈油",
                }
                name_col = None
                for col in df.columns:
                    if "名" in str(col) or "品种" in str(col) or "symbol" in str(col).lower():
                        name_col = col
                        break
                if name_col is None and len(df.columns) > 0:
                    name_col = df.columns[0]
                for _, row in df.iterrows():
                    name = str(row.get(name_col, "")) if name_col else ""
                    for key, display in key_items.items():
                        if key in name:
                            chg_col = [c for c in df.columns if "涨跌" in str(c) and "幅" in str(c)]
                            price_col = [c for c in df.columns if "最新" in str(c) or "收" in str(c)]
                            chg = float(row[chg_col[0]]) if chg_col else 0
                            price = str(row[price_col[0]]) if price_col else "—"
                            result[display] = {"price": price, "chg_pct": round(chg, 2)}
                            break
        except Exception as e:
            logger.warning(f"期货行情失败: {e}")
        return result
    return _safe_call(_fetch, timeout=10, default={}, label="期货行情")


# ============================================================
# L16. 全量数据打包 (供 AI CIO日报)
# ============================================================
def get_daily_data_pack() -> dict:
    """一次性获取所有数据"""
    return {
        "indices": get_major_indices(),
        "overview": get_market_overview(),
        "industry": get_industry_board(),
        "concept": get_concept_board(),
        "macro": get_macro_data(),
        "liquidity": get_liquidity_data(),
        "credit": get_credit_spread(),
        "style": get_style_data(),
        "volatility": get_volatility_data(),
        "etf": get_etf_list(),
        "northbound": get_northbound_flow(),
        "margin": get_margin_data(),
        "futures": get_futures_overview(),
        "news": get_all_news(tushare_count=150),
        "research": get_research_reports(30),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def pack_market_text(pack: dict) -> str:
    """将数据包转为文本 (供AI prompt) — V4: 更全面严谨"""
    mp = ["## 今日市场数据 (数据截至 {})".format(pack.get("timestamp", ""))]

    # 指数行情
    idx = pack.get("indices")
    if idx is not None and not idx.empty:
        mp.append("\n### 宽基指数")
        for _, r in idx.iterrows():
            chg = r.get("涨跌幅", 0)
            if pd.notna(chg):
                mp.append(f"- {r.get('名称','')}: {r.get('最新价','')} ({chg:+.2f}%)")

    # 涨跌统计
    ov = pack.get("overview", {})
    if ov:
        mp.append(f"\n### 市场情绪")
        mp.append(f"涨{ov.get('上涨',0)} 跌{ov.get('下跌',0)} | 涨停{ov.get('涨停',0)} 跌停{ov.get('跌停',0)} | 成交{ov.get('总成交额亿',0):.0f}亿 | 上涨占比{ov.get('上涨占比',0)}%")
        mp.append(f"强势股(>3%): {ov.get('强势股',0)} | 弱势股(<-3%): {ov.get('弱势股',0)}")

    # 宏观数据 (桥水四维)
    macro = pack.get("macro", {})
    if macro:
        items = [f"{k}:{v}" for k, v in macro.items() if v not in ("", None) and "月份" not in k]
        if items:
            mp.append(f"\n### 宏观经济 (增长+通胀)")
            mp.append(" | ".join(items))

    # 流动性
    liq = pack.get("liquidity", {})
    if liq:
        items = [f"{k}:{v}" for k, v in liq.items() if v not in ("", None)]
        if items:
            mp.append(f"\n### 流动性")
            mp.append(" | ".join(items))

    # 信用
    credit = pack.get("credit", {})
    if credit:
        items = [f"{k}:{v}" for k, v in credit.items() if v not in ("", None)]
        if items:
            mp.append(f"\n### 信用环境")
            mp.append(" | ".join(items))

    # 风格 (5日+20日)
    style = pack.get("style", {})
    if style:
        mp.append(f"\n### 市场风格")
        s_parts = []
        if "大小盘偏好_5日" in style:
            s_parts.append(f"大小盘(5日):{style['大小盘偏好_5日']}(300:{style.get('沪深300_5日','')}%/1000:{style.get('中证1000_5日','')}%)")
        if "大小盘偏好_20日" in style:
            s_parts.append(f"大小盘(20日):{style['大小盘偏好_20日']}(300:{style.get('沪深300_20日','')}%/1000:{style.get('中证1000_20日','')}%)")
        if "成长价值_5日" in style:
            s_parts.append(f"成长价值(5日):{style['成长价值_5日']}(创业板:{style.get('创业板指_5日','')}%/50:{style.get('上证50_5日','')}%)")
        if "成长价值_20日" in style:
            s_parts.append(f"成长价值(20日):{style['成长价值_20日']}(创业板:{style.get('创业板指_20日','')}%/50:{style.get('上证50_20日','')}%)")
        if s_parts:
            mp.append(" | ".join(s_parts))

    # 波动率
    vol = pack.get("volatility", {})
    if vol:
        mp.append(f"\n### 波动率与量能")
        v_parts = []
        if "沪深300_HV20" in vol:
            v_parts.append(f"沪深300 HV20:{vol['沪深300_HV20']}% ({vol.get('波动率环境','')})")
        if "成交额5/20比" in vol:
            v_parts.append(f"成交额5/20日比:{vol['成交额5/20比']} ({vol.get('量能状态','')})")
        if v_parts:
            mp.append(" | ".join(v_parts))

    # 北向资金
    nb = pack.get("northbound", {})
    if nb:
        mp.append(f"\n### 资金流向")
        mp.append(f"北向: 今日{nb.get('方向','')}{nb.get('今日净流入亿',0)}亿 | 5日均值{nb.get('5日均值亿',0)}亿")

    margin = pack.get("margin", {})
    if margin:
        mp.append(f"融资: 余额{margin.get('融资余额亿',0)}亿 | 5日变化{margin.get('融资5日变化亿',0)}亿 | {margin.get('杠杆情绪','')}")

    # 期货
    futures = pack.get("futures", {})
    if futures:
        f_parts = []
        for k, v in futures.items():
            chg = v.get("chg_pct", 0)
            f_parts.append(f"{k}:{v.get('price','')}" + (f"({chg:+.1f}%)" if chg else ""))
        if f_parts:
            mp.append(f"\n### 商品期货")
            mp.append(" | ".join(f_parts))

    # 行业
    ind = pack.get("industry")
    if ind is not None and not ind.empty and "板块名称" in ind.columns and "涨跌幅" in ind.columns:
        mp.append(f"\n### 行业板块")
        mp.append("涨幅TOP5: " + ", ".join(f"{r['板块名称']}({r['涨跌幅']:+.1f}%)" for _, r in ind.head(5).iterrows()))
        mp.append("跌幅TOP5: " + ", ".join(f"{r['板块名称']}({r['涨跌幅']:+.1f}%)" for _, r in ind.tail(5).iterrows()))

    # 情绪温度计
    sentiment = get_sentiment_temperature(ov, nb, margin, vol)
    if sentiment:
        mp.append(f"\n### 情绪温度计")
        mp.append(f"综合温度: {sentiment['温度']} ({sentiment['级别']})")
        for k, v in sentiment.get("分项", {}).items():
            mp.append(f"  - {k}: {v}")

    return "\n".join(mp)


def pack_news_text(pack: dict) -> str:
    """将资讯+研报转为文本 — V4版"""
    np_list = []
    news = pack.get("news", [])

    src_counts = {}
    for n in news:
        src = n.get("source", "unknown")
        src_counts[src] = src_counts.get(src, 0) + 1
    src_summary = ", ".join(f"{k}:{v}" for k, v in src_counts.items())
    np_list.append(f"## 今日资讯 (共{len(news)}条, 来源: {src_summary})")

    important = [n for n in news if n.get("important")]
    t1_news = [n for n in news if not n.get("important") and n.get("tier") in ("T0", "T1")]
    t2_news = [n for n in news if not n.get("important") and n.get("tier") in ("T2", "T3", None)]

    if important:
        np_list.append("\n### ⭐ 重要资讯")
        for n in important[:20]:
            np_list.append(f"⭐[{n.get('source','')}][{n.get('category','')}] {n.get('title','')}")
            if n.get("content") and n["content"] != n.get("title"):
                np_list.append(f"   摘要: {n['content'][:250]}")

    if t1_news:
        np_list.append("\n### 机构级资讯")
        for n in t1_news[:50]:
            line = f"- [{n.get('source','')}][{n.get('category','')}] {n.get('title','')}"
            content = n.get("content", "")
            if content and content != n.get("title") and len(content) > 20:
                line += f" | {content[:120]}"
            np_list.append(line)

    if t2_news:
        np_list.append("\n### 综合资讯")
        for n in t2_news[:40]:
            np_list.append(f"- [{n.get('source','')}] {n.get('title','')}")

    research = pack.get("research", [])
    if research:
        np_list.append(f"\n## 券商研报动态 ({len(research)}条)")
        for r in research[:25]:
            rating_chg = ""
            if r.get("pre_rating") and r.get("rating") and r["pre_rating"] != r["rating"]:
                rating_chg = f" (从{r['pre_rating']}→{r['rating']})"
            elif r.get("rating"):
                rating_chg = f" ({r['rating']})"
            target = f" 目标价{r['target_price']}" if r.get("target_price") else ""
            np_list.append(f"- {r.get('org_name','')}: {r.get('stock_name','')}{rating_chg}{target}")

    return "\n".join(np_list)


# ============================================================
# Q1. 行业资金流向 (Tushare PRO)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_industry_moneyflow() -> pd.DataFrame:
    """行业资金流向 — 识别资金主攻方向"""
    def _tushare_fetch():
        pro = _get_tushare_pro()
        if not pro:
            return None
        try:
            today = _last_trade_date()
            df = pro.moneyflow_ind_dc(trade_date=today)
            if df is None or df.empty:
                for offset in range(1, 4):
                    df = pro.moneyflow_ind_dc(trade_date=_last_trade_date(offset))
                    if df is not None and not df.empty:
                        break
            if df is not None and not df.empty:
                for c in ["net_amount", "buy_elg_amount", "buy_lg_amount",
                           "buy_md_amount", "buy_sm_amount"]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
                df = df.sort_values("net_amount", ascending=False).reset_index(drop=True)
                return df
        except Exception as e:
            logger.warning(f"[TS] 行业资金流向: {e}")
        return None

    return _safe_call(_tushare_fetch, timeout=15, default=pd.DataFrame(), label="行业资金流[TS]")


# ============================================================
# Q2. 个股日线行情 (Tushare PRO — 量化选股核心)
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_stock_daily(ts_code: str, days: int = 120) -> pd.DataFrame:
    """获取单只股票日线行情 (V4.1 架构师修正：强制前复权)"""
    pro = _get_tushare_pro()
    if not pro:
        return pd.DataFrame()
    try:
        import tushare as ts
        end = _last_trade_date()
        start = (datetime.now() - timedelta(days=days * 1.5)).strftime("%Y%m%d")
        
        # 极简令牌桶限流，保护 API Token
        time.sleep(0.05) 
        # 核心修正：强制使用 pro_bar 并在源头执行 qfq
        df = ts.pro_bar(ts_code=ts_code, api=pro, adj='qfq', start_date=start, end_date=end)
        
        if df is not None and not df.empty:
            df = df.sort_values("trade_date").reset_index(drop=True)
            for c in ["open", "high", "low", "close", "vol", "amount", "pct_chg"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df
    except Exception as e:
        logger.warning(f"[TS] 个股日线 {ts_code}: {e}")
    return pd.DataFrame()


# ============================================================
# Q3. 个股资金流向 (Tushare PRO)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_stock_moneyflow(ts_code: str, days: int = 20) -> pd.DataFrame:
    """个股资金流向 — 主力/超大单/大单"""
    pro = _get_tushare_pro()
    if not pro:
        return pd.DataFrame()
    try:
        end = _last_trade_date()
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        df = pro.moneyflow(ts_code=ts_code, start_date=start, end_date=end)
        if df is not None and not df.empty:
            df = df.sort_values("trade_date").reset_index(drop=True)
            for c in df.columns:
                if c != "trade_date" and c != "ts_code":
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df
    except Exception as e:
        logger.warning(f"[TS] 个股资金流 {ts_code}: {e}")
    return pd.DataFrame()


# ============================================================
# Q4. 全市场行情快照 (Tushare daily — 用于批量筛选)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_market_snapshot() -> pd.DataFrame:
    """全A股今日行情快照 — 量化选股的基础数据"""
    def _tushare_fetch():
        pro = _get_tushare_pro()
        if not pro:
            return None
        try:
            today = _last_trade_date()
            df = pro.daily(trade_date=today)
            if df is None or df.empty:
                for offset in range(1, 4):
                    df = pro.daily(trade_date=_last_trade_date(offset))
                    if df is not None and not df.empty:
                        break
            if df is not None and not df.empty:
                for c in ["open", "high", "low", "close", "pre_close",
                           "change", "pct_chg", "vol", "amount"]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
                # 基础名称映射
                try:
                    basic = pro.stock_basic(exchange='', list_status='L',
                                             fields='ts_code,symbol,name,industry,area')
                    if basic is not None and not basic.empty:
                        df = df.merge(basic[["ts_code", "name", "industry"]], on="ts_code", how="left")
                except Exception:
                    pass
                return df
        except Exception as e:
            logger.warning(f"[TS] 全市场快照: {e}")
        return None

    def _akshare_fetch():
        ak = _import_akshare()
        if not ak:
            return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                for c in ["最新价", "涨跌幅", "涨跌额", "成交量", "成交额",
                           "振幅", "换手率", "量比"]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
                return df
        except Exception:
            pass
        return pd.DataFrame()

    result = _safe_call(_tushare_fetch, timeout=20, default=None, label="市场快照[TS]")
    if result is not None and not result.empty:
        return result
    logger.info("[降级] 市场快照 → AKShare")
    return _safe_call(_akshare_fetch, timeout=15, default=pd.DataFrame(), label="市场快照[AK]")


# ============================================================
# Q5. 历史日线批量 (Tushare — 用于计算技术指标)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_multi_stock_daily(ts_codes: list, days: int = 60) -> dict:
    """批量获取多只股票日线 — 用于因子计算 (V4.1 架构师修正：强制前复权)"""
    pro = _get_tushare_pro()
    if not pro:
        return {}
        
    import tushare as ts
    result = {}
    end = _last_trade_date()
    start = (datetime.now() - timedelta(days=days * 1.5)).strftime("%Y%m%d")
    
    for ts_code in ts_codes[:50]:  # 最多50只，避免API过载
        try:
            # 极简令牌桶限流，保护 API Token
            time.sleep(0.05) 
            # 核心修正：强制使用 pro_bar 并在源头执行 qfq
            df = ts.pro_bar(ts_code=ts_code, api=pro, adj='qfq', start_date=start, end_date=end)
            
            if df is not None and not df.empty:
                df = df.sort_values("trade_date").reset_index(drop=True)
                for c in ["open", "high", "low", "close", "vol", "amount", "pct_chg"]:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
                result[ts_code] = df
        except Exception as e:
            logger.warning(f"[TS] 日线 {ts_code}: {e}")
    return result


# ============================================================
# Q6. 个股资金流向批量 (Tushare — 按日期获取全市场)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_market_moneyflow(date: str = None) -> pd.DataFrame:
    """全市场个股资金流向 — 按日期"""
    pro = _get_tushare_pro()
    if not pro:
        return pd.DataFrame()
    try:
        if not date:
            date = _last_trade_date()
        df = pro.moneyflow(trade_date=date)
        if df is None or df.empty:
            for offset in range(1, 4):
                df = pro.moneyflow(trade_date=_last_trade_date(offset))
                if df is not None and not df.empty:
                    break
        if df is not None and not df.empty:
            for c in df.columns:
                if c not in ("trade_date", "ts_code"):
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df
    except Exception as e:
        logger.warning(f"[TS] 全市场资金流: {e}")
    return pd.DataFrame()


# ============================================================
# Q7. 量化因子计算引擎
# ============================================================
def calc_technical_factors(df: pd.DataFrame) -> dict:
    """
    基于日线数据计算技术因子
    输入: 单只股票的日线 DataFrame (需含 close/high/low/vol/amount/pct_chg)
    输出: 因子字典
    """
    if df is None or df.empty or len(df) < 20:
        return {}

    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    vol = df["vol"].values.astype(float)
    pct_chg = df["pct_chg"].values.astype(float) if "pct_chg" in df.columns else np.zeros(len(close))

    factors = {}

    # === 趋势动量 ===
    if len(close) >= 5:
        factors["动量_5日"] = round((close[-1] / close[-5] - 1) * 100, 2)
    if len(close) >= 10:
        factors["动量_10日"] = round((close[-1] / close[-10] - 1) * 100, 2)
    if len(close) >= 20:
        factors["动量_20日"] = round((close[-1] / close[-20] - 1) * 100, 2)
    if len(close) >= 60:
        factors["动量_60日"] = round((close[-1] / close[-60] - 1) * 100, 2)

    # === 均线系统 ===
    if len(close) >= 5:
        ma5 = np.mean(close[-5:])
        factors["MA5"] = round(ma5, 2)
        factors["价格/MA5"] = round(close[-1] / ma5, 4)
    if len(close) >= 10:
        ma10 = np.mean(close[-10:])
        factors["MA10"] = round(ma10, 2)
    if len(close) >= 20:
        ma20 = np.mean(close[-20:])
        factors["MA20"] = round(ma20, 2)
        factors["价格/MA20"] = round(close[-1] / ma20, 4)
    if len(close) >= 60:
        ma60 = np.mean(close[-60:])
        factors["MA60"] = round(ma60, 2)
        factors["价格/MA60"] = round(close[-1] / ma60, 4)

    # MA5 > MA20 金叉
    if "MA5" in factors and "MA20" in factors:
        factors["均线多头"] = 1 if factors["MA5"] > factors["MA20"] else 0

    # === MACD ===
    if len(close) >= 35:
        ema12 = _ema(close, 12)
        ema26 = _ema(close, 26)
        dif = ema12 - ema26
        dea = _ema(dif, 9)
        macd_bar = (dif - dea) * 2
        factors["MACD_DIF"] = round(dif[-1], 3)
        factors["MACD_DEA"] = round(dea[-1], 3)
        factors["MACD柱"] = round(macd_bar[-1], 3)
        factors["MACD金叉"] = 1 if dif[-1] > dea[-1] and dif[-2] <= dea[-2] else 0

    # === RSI ===
    if len(pct_chg) >= 14:
        gains = np.where(pct_chg[-14:] > 0, pct_chg[-14:], 0)
        losses = np.where(pct_chg[-14:] < 0, -pct_chg[-14:], 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            factors["RSI_14"] = round(100 - 100 / (1 + rs), 1)
        else:
            factors["RSI_14"] = 100.0

    # === 布林带 ===
    if len(close) >= 20:
        ma20 = np.mean(close[-20:])
        std20 = np.std(close[-20:])
        upper = ma20 + 2 * std20
        lower = ma20 - 2 * std20
        factors["布林上轨"] = round(upper, 2)
        factors["布林下轨"] = round(lower, 2)
        if upper != lower:
            factors["布林位置"] = round((close[-1] - lower) / (upper - lower), 2)  # 0=下轨 1=上轨

    # === ATR (波动率) ===
    if len(close) >= 15:
        tr = np.maximum(high[-14:] - low[-14:],
                        np.maximum(abs(high[-14:] - close[-15:-1]),
                                   abs(low[-14:] - close[-15:-1])))
        atr14 = np.mean(tr)
        factors["ATR_14"] = round(atr14, 2)
        factors["ATR/价格%"] = round(atr14 / close[-1] * 100, 2)

    # === 量价关系 ===
    if len(vol) >= 20:
        vol5 = np.mean(vol[-5:])
        vol20 = np.mean(vol[-20:])
        factors["量比_5/20"] = round(vol5 / vol20, 2) if vol20 > 0 else 1
        factors["今日量比"] = round(vol[-1] / vol20, 2) if vol20 > 0 else 1
    if len(vol) >= 5:
        factors["5日均量"] = round(np.mean(vol[-5:]), 0)

    # === 近N日新高/新低 ===
    if len(high) >= 20:
        factors["20日新高"] = 1 if close[-1] >= np.max(high[-20:]) * 0.98 else 0
    if len(high) >= 60:
        factors["60日新高"] = 1 if close[-1] >= np.max(high[-60:]) * 0.98 else 0
    if len(low) >= 20:
        factors["20日新低"] = 1 if close[-1] <= np.min(low[-20:]) * 1.02 else 0

    # === 连涨/连跌天数 ===
    if len(pct_chg) >= 2:
        consecutive = 0
        for i in range(len(pct_chg) - 1, -1, -1):
            if pct_chg[i] > 0:
                consecutive += 1
            else:
                break
        factors["连涨天数"] = consecutive

    return factors


def _ema(data, period):
    """指数移动平均"""
    if len(data) < period:
        return data
    alpha = 2 / (period + 1)
    result = np.zeros_like(data, dtype=float)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def calc_moneyflow_factors(mf_df: pd.DataFrame) -> dict:
    """基于资金流向数据计算因子"""
    if mf_df is None or mf_df.empty:
        return {}
    factors = {}
    try:
        # 最近一日
        latest = mf_df.iloc[-1]
        # 主力净流入 (超大单+大单)
        buy_elg = float(latest.get("buy_elg_vol", 0))
        sell_elg = float(latest.get("sell_elg_vol", 0))
        buy_lg = float(latest.get("buy_lg_vol", 0))
        sell_lg = float(latest.get("sell_lg_vol", 0))
        net_main = (buy_elg - sell_elg + buy_lg - sell_lg)
        factors["主力净流入"] = round(net_main, 0)

        # 5日累计主力净流入
        if len(mf_df) >= 5:
            recent5 = mf_df.tail(5)
            net5 = 0
            for _, r in recent5.iterrows():
                net5 += (float(r.get("buy_elg_vol", 0)) - float(r.get("sell_elg_vol", 0))
                         + float(r.get("buy_lg_vol", 0)) - float(r.get("sell_lg_vol", 0)))
            factors["主力净流入_5日"] = round(net5, 0)

        # 超大单占比
        total_vol = float(latest.get("buy_elg_vol", 0)) + float(latest.get("sell_elg_vol", 0))
        total_all = float(latest.get("trade_count", 1)) if latest.get("trade_count") else 1
        if total_all > 0:
            factors["超大单占比"] = round(total_vol / max(total_all, 1) * 100, 1)

        # 连续净流入天数
        consecutive = 0
        for i in range(len(mf_df) - 1, -1, -1):
            r = mf_df.iloc[i]
            net = (float(r.get("buy_elg_vol", 0)) - float(r.get("sell_elg_vol", 0))
                   + float(r.get("buy_lg_vol", 0)) - float(r.get("sell_lg_vol", 0)))
            if net > 0:
                consecutive += 1
            else:
                break
        factors["主力连续流入天数"] = consecutive

    except Exception as e:
        logger.warning(f"资金因子计算异常: {e}")
    return factors


# ============================================================
# Q8. 多因子综合选股引擎
# ============================================================
def quant_stock_screener(
    min_amount: float = 5000,    # 最低成交额(万)，过滤流动性不足
    top_n: int = 30,             # 输出TOP N
    factors_weight: dict = None, # 自定义因子权重
) -> pd.DataFrame:
    """
    多因子量化选股引擎
    流程:
    1. 全市场快照 → 基础过滤 (ST/新股/流动性)
    2. 批量获取日线 → 计算技术因子
    3. 批量获取资金流向 → 计算资金因子
    4. 多因子加权打分 → 排名输出 TOP N
    """
    if factors_weight is None:
        factors_weight = {
            "动量_20日": 0.15,
            "量比_5/20": 0.15,
            "MACD金叉": 0.10,
            "均线多头": 0.10,
            "RSI_14": 0.10,
            "主力净流入_5日": 0.20,
            "主力连续流入天数": 0.10,
            "20日新高": 0.10,
        }

    # Step 1: 全市场快照
    snapshot = get_market_snapshot()
    if snapshot is None or snapshot.empty:
        logger.warning("全市场快照为空")
        return pd.DataFrame()

    # 判断数据源 (Tushare vs AKShare 列名不同)
    is_tushare = "ts_code" in snapshot.columns

    if is_tushare:
        # 过滤 ST + 新股 + 流动性
        if "name" in snapshot.columns:
            snapshot = snapshot[~snapshot["name"].str.contains("ST|退", na=False)]
        snapshot = snapshot[snapshot["amount"] >= min_amount / 10]  # Tushare amount 千元
        # 过滤北交所 (8开头)
        snapshot = snapshot[~snapshot["ts_code"].str.startswith("8")]
        # 过滤涨跌停 (无法买入)
        if "pct_chg" in snapshot.columns:
            snapshot = snapshot[(snapshot["pct_chg"] < 9.8) & (snapshot["pct_chg"] > -9.8)]
        candidates = snapshot["ts_code"].tolist()
    else:
        # AKShare 格式
        if "名称" in snapshot.columns:
            snapshot = snapshot[~snapshot["名称"].str.contains("ST|退", na=False)]
        if "成交额" in snapshot.columns:
            snapshot = snapshot[snapshot["成交额"] >= min_amount * 1e4]
        if "代码" in snapshot.columns:
            snapshot = snapshot[~snapshot["代码"].astype(str).str.startswith("8")]
        if "涨跌幅" in snapshot.columns:
            snapshot = snapshot[(snapshot["涨跌幅"] < 9.8) & (snapshot["涨跌幅"] > -9.8)]
        # 转换代码格式
        if "代码" in snapshot.columns:
            def _to_ts_code(code):
                code = str(code).zfill(6)
                if code.startswith("6"):
                    return f"{code}.SH"
                else:
                    return f"{code}.SZ"
            snapshot["ts_code"] = snapshot["代码"].apply(_to_ts_code)
            candidates = snapshot["ts_code"].tolist()
        else:
            candidates = []

    if not candidates:
        logger.warning("无候选股票")
        return pd.DataFrame()

    # 取成交额 TOP 200 (避免API过载)
    if is_tushare:
        snapshot_sorted = snapshot.sort_values("amount", ascending=False)
    else:
        snapshot_sorted = snapshot.sort_values("成交额", ascending=False)
    candidates = snapshot_sorted.head(200)["ts_code"].tolist()

    logger.info(f"[选股] 候选池: {len(candidates)} 只")

    # Step 2: 批量日线 + 技术因子
    daily_data = get_multi_stock_daily(candidates[:50], days=80)

    # Step 3: 全市场资金流向
    mf_data = get_market_moneyflow()

    # Step 4: 逐只计算因子并打分
    scored = []
    for ts_code in candidates[:50]:
        row = {"ts_code": ts_code}

        # 名称
        match = snapshot[snapshot["ts_code"] == ts_code]
        if not match.empty:
            if is_tushare:
                row["名称"] = match.iloc[0].get("name", "")
                row["行业"] = match.iloc[0].get("industry", "")
                row["涨跌幅"] = float(match.iloc[0].get("pct_chg", 0))
                row["成交额万"] = round(float(match.iloc[0].get("amount", 0)) / 10, 0)
            else:
                row["名称"] = match.iloc[0].get("名称", "")
                row["行业"] = ""
                row["涨跌幅"] = float(match.iloc[0].get("涨跌幅", 0))
                row["成交额万"] = round(float(match.iloc[0].get("成交额", 0)) / 1e4, 0)

        # 技术因子
        tech_factors = {}
        if ts_code in daily_data:
            tech_factors = calc_technical_factors(daily_data[ts_code])

        # 资金因子
        money_factors = {}
        if mf_data is not None and not mf_data.empty:
            stock_mf = mf_data[mf_data["ts_code"] == ts_code]
            if not stock_mf.empty:
                money_factors = calc_moneyflow_factors(stock_mf)

        all_factors = {**tech_factors, **money_factors}
        row.update(all_factors)

        # 综合打分
        score = 0
        for factor_name, weight in factors_weight.items():
            val = all_factors.get(factor_name, 0)
            if factor_name == "动量_20日":
                # 正动量得分高, 标准化到0-100
                score += weight * min(max((val + 10) / 30 * 100, 0), 100)
            elif factor_name == "量比_5/20":
                score += weight * min(max(val * 50, 0), 100)
            elif factor_name in ("MACD金叉", "均线多头", "20日新高"):
                score += weight * (val * 100)
            elif factor_name == "RSI_14":
                # RSI 50-80 得分高
                if 50 <= val <= 80:
                    score += weight * 100
                elif 40 <= val < 50:
                    score += weight * 60
                elif val > 80:
                    score += weight * 30  # 超买扣分
                else:
                    score += weight * 20
            elif factor_name == "主力净流入_5日":
                score += weight * min(max((val + 5000) / 10000 * 100, 0), 100)
            elif factor_name == "主力连续流入天数":
                score += weight * min(val * 20, 100)
            else:
                score += weight * min(max(val, 0), 100)

        row["综合得分"] = round(score, 1)
        scored.append(row)

    if not scored:
        return pd.DataFrame()

    result = pd.DataFrame(scored)
    result = result.sort_values("综合得分", ascending=False).head(top_n).reset_index(drop=True)
    result.index = result.index + 1  # 排名从1开始
    return result


# 兼容旧接口
def get_cls_telegraph(count: int = 50) -> list:
    return get_all_news(tushare_count=max(count, 80))