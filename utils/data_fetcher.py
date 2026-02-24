"""
数据采集模块 - 寻星情报中心 (双擎版)
包含：AKShare 行情数据 + Tushare PRO 机构级多源资讯接口
"""
import akshare as ak
import tushare as ts
import pandas as pd
import requests
import json
import time
import os
import concurrent.futures
from datetime import datetime, timedelta
import streamlit as st
import urllib3
import certifi
import shutil

# 1. 屏蔽本地代理软件可能引发的 SSL 证书警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 2. 修复 Python 路径含中文导致的底层 curl SSL 证书找不到的 Bug
try:
    safe_cert_path = os.path.join(os.getcwd(), "cacert.pem")
    if not os.path.exists(safe_cert_path):
        shutil.copy(certifi.where(), safe_cert_path)
    os.environ["CURL_CA_BUNDLE"] = safe_cert_path
    os.environ["REQUESTS_CA_BUNDLE"] = safe_cert_path
except Exception as e:
    print(f"[环境修复] SSL证书路径修复失败: {e}")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)

def _safe_call(func, timeout=8, default=None):
    """带超时的安全调用，统一缩短至 8 秒"""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        print(f"[超时拦截] 请求超过 {timeout} 秒强制切断。")
        return default
    except Exception as e:
        print(f"[接口报错] 获取异常: {str(e)}")
        return default

# ============================================================
# Tushare 初始化配置
# ============================================================
def _get_tushare_pro():
    """获取并初始化 Tushare Pro 接口"""
    try:
        token = st.secrets.get("TUSHARE_TOKEN", "")
        if token:
            ts.set_token(token)
            return ts.pro_api()
    except Exception as e:
        print(f"[Tushare 错误] 初始化失败: {e}")
    return None

# ============================================================
# 1-5 行情概况与宏观等基础函数 (AKShare 提供)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_major_indices() -> pd.DataFrame:
    def _fetch():
        df = ak.stock_zh_index_spot_em()
        if df is None or df.empty: return pd.DataFrame()
        target = ["上证指数", "深证成指", "创业板指", "科创50", "沪深300", "中证500", "中证1000"]
        result = df[df["名称"].isin(target)].copy()
        keep_cols = [c for c in ["名称", "最新价", "涨跌幅", "涨跌额", "成交额"] if c in result.columns]
        result = result[keep_cols].reset_index(drop=True)
        for c in ["最新价", "涨跌幅", "涨跌额", "成交额"]:
            if c in result.columns: result[c] = pd.to_numeric(result[c], errors="coerce")
        return result
    return _safe_call(_fetch, timeout=8, default=pd.DataFrame())

@st.cache_data(ttl=600, show_spinner=False)
def get_market_overview() -> dict:
    def _fetch():
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty: return {}
        df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
        df["成交额"] = pd.to_numeric(df["成交额"], errors="coerce")
        total = len(df)
        up = int((df["涨跌幅"] > 0).sum())
        down = int((df["涨跌幅"] < 0).sum())
        flat = total - up - down
        limit_up = int((df["涨跌幅"] >= 9.8).sum())
        limit_down = int((df["涨跌幅"] <= -9.8).sum())
        total_amount = round(df["成交额"].sum() / 1e8, 0)
        return {"上涨": up, "下跌": down, "平盘": flat, "涨停": limit_up, "跌停": limit_down, "总成交额亿": total_amount, "上涨占比": round(up / total * 100, 1) if total else 0}
    return _safe_call(_fetch, timeout=8, default={})

@st.cache_data(ttl=900, show_spinner=False)
def get_industry_board() -> pd.DataFrame:
    def _fetch():
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            for c in ["涨跌幅", "总市值", "换手率"]:
                if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
        return pd.DataFrame()
    return _safe_call(_fetch, timeout=8, default=pd.DataFrame())

@st.cache_data(ttl=900, show_spinner=False)
def get_concept_board() -> pd.DataFrame:
    def _fetch():
        df = ak.stock_board_concept_name_em()
        if df is not None and not df.empty:
            for c in ["涨跌幅", "总市值", "换手率"]:
                if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
        return pd.DataFrame()
    return _safe_call(_fetch, timeout=8, default=pd.DataFrame())

@st.cache_data(ttl=7200, show_spinner=False)
def get_macro_data() -> dict:
    def _fetch():
        macro = {"CPI同比": "—", "制造业PMI": "—", "中国10Y国债": "—", "美国10Y国债": "—"}
        try:
            df = ak.macro_china_cpi_monthly()
            if df is not None and not df.empty: macro["CPI同比"] = str(df.iloc[-1].iloc[-1])
        except: pass
        try:
            df = ak.macro_china_pmi()
            if df is not None and not df.empty: macro["制造业PMI"] = str(df.iloc[-1].iloc[-1])
        except: pass
        try:
            df = ak.bond_zh_us_rate(start_date="20250101")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                for col in df.columns:
                    if "中国" in str(col) and "10" in str(col): macro["中国10Y国债"] = f"{latest[col]}%"
                    if "美国" in str(col) and "10" in str(col): macro["美国10Y国债"] = f"{latest[col]}%"
        except: pass
        return macro
    return _safe_call(_fetch, timeout=8, default={"CPI同比": "超时", "制造业PMI": "超时"})

@st.cache_data(ttl=600, show_spinner=False)
def get_style_data() -> dict:
    def _fetch():
        hs300 = ak.stock_zh_index_daily_em(symbol="sh000300")
        zz1000 = ak.stock_zh_index_daily_em(symbol="sh000852")
        if hs300 is not None and len(hs300) >= 6 and zz1000 is not None and len(zz1000) >= 6:
            hs_5d = (float(hs300.iloc[-1]["close"]) / float(hs300.iloc[-6]["close"]) - 1) * 100
            zz_5d = (float(zz1000.iloc[-1]["close"]) / float(zz1000.iloc[-6]["close"]) - 1) * 100
            return {"沪深300_5日": round(hs_5d, 2), "中证1000_5日": round(zz_5d, 2), "偏好": "偏大盘" if hs_5d > zz_5d else "偏小盘"}
        return {}
    return _safe_call(_fetch, timeout=8, default={})

# ============================================================
# 6. 资讯中心 (多源 Tushare PRO 机构专线 + 严格清洗)
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_cls_telegraph(count: int = 50) -> list:
    """使用 Tushare PRO 获取多源标准化资讯 (同花顺/华尔街见闻/东财/新浪)"""
    telegraphs = []
    pro = _get_tushare_pro()
    
    if not pro:
        st.warning("⚠️ 尚未配置 TUSHARE_TOKEN 或 Token 无效")
        return []

    # 【漏斗规则配置】
    noise_words = ["互动平台", "互动易", "晚会", "抽奖", "投资者关系", "提醒", "交易提示", 
                   "停牌", "复牌", "新股申购", "原油API", "EIA", "美联储官员", "美联储理事", "公告", "大宗交易", "调研信息"]
    overseas_words = ["美股", "美联储", "美元", "美债", "日经", "日股", "韩国", "欧洲", "纳指", "道指"]
    
    overseas_limit = int(count * 0.3)
    overseas_current = 0

    # 【核心升级】Tushare 顶级数据源优先级梯队 (A股散户风向标 -> 机构宏观视角 -> 大众门户)
    sources_priority = {
        "10jqka": "同花顺",
        "wallstreetcn": "华尔街见闻",
        "eastmoney": "东方财富",
        "sina": "新浪财经"
    }

    try:
        # 提取过去 2 天的数据作为数据池
        now = datetime.now()
        start_time = (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
        end_time = now.strftime('%Y-%m-%d %H:%M:%S')

        # 按优先级依次轮询数据源，直到填满用户需要的 count (如300条)
        for src_code, src_name in sources_priority.items():
            if len(telegraphs) >= count:
                break
                
            # 每个源单次索取最大 500 条原始数据交由漏斗清洗
            df = pro.news(src=src_code, start_date=start_time, end_date=end_time, limit=500)
            
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    if len(telegraphs) >= count: break
                    
                    # 1. 提取并清理 None/NaN 幽灵
                    raw_title = row.get('title')
                    raw_content = row.get('content')
                    
                    title = str(raw_title).strip() if pd.notna(raw_title) else ""
                    content = str(raw_content).strip() if pd.notna(raw_content) else ""
                    
                    # 强制干掉被 Pandas 转义的文字版 "None" 和 "nan"
                    if title.lower() in ["none", "nan", ""]: title = ""
                    if content.lower() in ["none", "nan", ""]: content = ""
                    
                    if not title and not content:
                        continue
                        
                    # 2. 标题内容互补修复
                    if not title:
                        title = content[:60] + "..."
                    if not content:
                        content = title
                        
                    full_text = title + content
                    
                    # 3. 严格去重与漏斗过滤
                    if any(title in t["title"] for t in telegraphs): continue
                    if any(w in full_text for w in noise_words): continue
                    if any(w in full_text for w in overseas_words):
                        if overseas_current >= overseas_limit: continue
                        overseas_current += 1

                    # 4. 时间格式化
                    time_str = str(row.get('datetime', ''))
                    pub_time = time_str.split(" ")[1][:5] if " " in time_str else time_str
                    
                    telegraphs.append({
                        "time": pub_time, 
                        "title": title, 
                        "content": content, 
                        "important": False, 
                        "source": src_name
                    })

    except Exception as e:
        print(f"[报错诊断] Tushare多源聚合失败: {e}")

    return telegraphs[:count]

# ============================================================
# 7. ETF行情
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_etf_list() -> pd.DataFrame:
    def _fetch():
        df = ak.fund_etf_spot_em()
        if df is not None and not df.empty:
            for c in ["最新价", "涨跌幅", "成交额"]:
                if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.head(50).reset_index(drop=True)
        return pd.DataFrame()
    return _safe_call(_fetch, timeout=8, default=pd.DataFrame())