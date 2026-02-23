"""
数据采集模块 - AKShare + 财联社 + 东方财富
优化：超时控制 + 错误隔离 + 缓存
"""

import akshare as ak
import pandas as pd
import requests
import json
import time
import os
import concurrent.futures
from datetime import datetime
from bs4 import BeautifulSoup
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _safe_call(func, timeout=20, default=None):
    """带超时的安全调用，防止单个接口卡住整个页面"""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return default
    except Exception:
        return default


# ============================================================
# 1. 指数行情
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def get_major_indices() -> pd.DataFrame:
    """获取主要指数实时行情"""
    def _fetch():
        df = ak.stock_zh_index_spot_em()
        if df is None or df.empty:
            return pd.DataFrame()
        target = ["上证指数", "深证成指", "创业板指", "科创50", "沪深300", "中证500", "中证1000"]
        result = df[df["名称"].isin(target)].copy()
        keep_cols = [c for c in ["名称", "最新价", "涨跌幅", "涨跌额", "成交额"] if c in result.columns]
        result = result[keep_cols].reset_index(drop=True)
        for c in ["最新价", "涨跌幅", "涨跌额", "成交额"]:
            if c in result.columns:
                result[c] = pd.to_numeric(result[c], errors="coerce")
        return result

    result = _safe_call(_fetch, timeout=15, default=pd.DataFrame())
    return result if result is not None else pd.DataFrame()


# ============================================================
# 2. 市场涨跌概况
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def get_market_overview() -> dict:
    """全A涨跌统计"""
    def _fetch():
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
        return {
            "上涨": up, "下跌": down, "平盘": flat,
            "涨停": limit_up, "跌停": limit_down,
            "总成交额亿": total_amount,
            "上涨占比": round(up / total * 100, 1) if total else 0,
        }

    result = _safe_call(_fetch, timeout=20, default={})
    return result if result else {}


# ============================================================
# 3. 板块数据
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def get_industry_board() -> pd.DataFrame:
    """行业板块行情"""
    def _fetch():
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            for c in ["涨跌幅", "总市值", "换手率"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
        return pd.DataFrame()

    result = _safe_call(_fetch, timeout=15, default=pd.DataFrame())
    return result if result is not None else pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def get_concept_board() -> pd.DataFrame:
    """概念板块行情"""
    def _fetch():
        df = ak.stock_board_concept_name_em()
        if df is not None and not df.empty:
            for c in ["涨跌幅", "总市值", "换手率"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
        return pd.DataFrame()

    result = _safe_call(_fetch, timeout=15, default=pd.DataFrame())
    return result if result is not None else pd.DataFrame()


# ============================================================
# 4. 宏观数据
# ============================================================

@st.cache_data(ttl=7200, show_spinner=False)
def get_macro_data() -> dict:
    """关键宏观指标"""
    macro = {}

    try:
        df = ak.macro_china_cpi_monthly()
        if df is not None and not df.empty:
            macro["CPI同比"] = str(df.iloc[-1].iloc[-1])
    except Exception:
        macro["CPI同比"] = "—"

    try:
        df = ak.macro_china_pmi()
        if df is not None and not df.empty:
            macro["制造业PMI"] = str(df.iloc[-1].iloc[-1])
    except Exception:
        macro["制造业PMI"] = "—"

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

    return macro


# ============================================================
# 5. 市场风格
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def get_style_data() -> dict:
    """大小盘风格指标"""
    def _fetch():
        hs300 = ak.stock_zh_index_daily_em(symbol="sh000300")
        zz1000 = ak.stock_zh_index_daily_em(symbol="sh000852")
        if hs300 is not None and len(hs300) >= 6 and zz1000 is not None and len(zz1000) >= 6:
            hs_5d = (float(hs300.iloc[-1]["close"]) / float(hs300.iloc[-6]["close"]) - 1) * 100
            zz_5d = (float(zz1000.iloc[-1]["close"]) / float(zz1000.iloc[-6]["close"]) - 1) * 100
            return {
                "沪深300_5日": round(hs_5d, 2),
                "中证1000_5日": round(zz_5d, 2),
                "偏好": "偏大盘" if hs_5d > zz_5d else "偏小盘",
            }
        return {}

    result = _safe_call(_fetch, timeout=15, default={})
    return result if result else {}


# ============================================================
# 6. 财联社电报
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_cls_telegraph(count: int = 50) -> list:
    """财联社实时电报"""
    telegraphs = []
    try:
        url = "https://www.cls.cn/nodeapi/updateTelegraph"
        params = {"app": "CailianpressWeb", "os": "web", "sv": "7.7.5", "rn": str(count)}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.cls.cn/telegraph",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("roll_data", [])
            for item in items:
                content = item.get("content", "")
                title = item.get("title", "") or content[:60]
                # 清理HTML
                for text_field in [content, title]:
                    if "<" in text_field:
                        try:
                            text_field = BeautifulSoup(text_field, "lxml").get_text()
                        except Exception:
                            pass

                ts = item.get("ctime", 0)
                pub_time = datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""
                important = item.get("level", "") == "B" or item.get("recommend", 0) > 0

                telegraphs.append({
                    "time": pub_time,
                    "title": BeautifulSoup(title, "lxml").get_text() if "<" in title else title,
                    "content": BeautifulSoup(content, "lxml").get_text() if "<" in content else content,
                    "important": important,
                    "source": "财联社",
                })
    except Exception:
        pass

    # 备用: 东方财富快讯
    if not telegraphs:
        try:
            df = ak.stock_news_em(symbol="全部")
            if df is not None and not df.empty:
                for _, row in df.head(count).iterrows():
                    telegraphs.append({
                        "time": str(row.get("发布时间", ""))[-8:],
                        "title": str(row.get("新闻标题", "")),
                        "content": str(row.get("新闻内容", ""))[:300],
                        "important": False,
                        "source": "东方财富",
                    })
        except Exception:
            pass

    return telegraphs


# ============================================================
# 7. ETF行情
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def get_etf_list() -> pd.DataFrame:
    """主要ETF行情"""
    try:
        df = ak.fund_etf_spot_em()
        if df is not None and not df.empty:
            for c in ["最新价", "涨跌幅", "成交额"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.head(50).reset_index(drop=True)
    except Exception:
        pass
    return pd.DataFrame()
