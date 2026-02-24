"""
数据采集模块 - 寻星情报中心专属原生直连引擎
军规级优化：全局超时控制 + 三级清洗漏斗 + 原生API直连 + 自动翻页引擎
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
# 1-5 行情概况与宏观等基础函数
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
# 6. 资讯中心 (完全体：多页滚动提取 + 三级去噪漏斗)
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_cls_telegraph(count: int = 50) -> list:
    """自动翻页获取，确保经过严格清洗后依然能达到指定数量"""
    telegraphs = []
    
    # 【漏斗规则配置】
    noise_words = ["互动平台", "互动易", "晚会", "抽奖", "投资者关系", "提醒", "交易提示", 
                   "停牌", "复牌", "新股申购", "原油API", "EIA", "美联储官员", "美联储理事", "公告", "大宗交易", "调研信息"]
    overseas_words = ["美股", "美联储", "美元", "美债", "日经", "日股", "韩国", "欧洲", "纳指", "道指"]
    
    overseas_limit = int(count * 0.3)
    overseas_current = 0

    # 1. 新浪财经原生底层 (支持翻页，最多翻 6 页)
    try:
        for page in range(1, 7):
            if len(telegraphs) >= count: break
            url = f"https://zhibo.sina.com.cn/api/zhibo/feed?page={page}&page_size=200&zhibo_id=152&tag_id=0&dire=f&dpc=1"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
            resp = requests.get(url, headers=headers, timeout=5, verify=False)
            
            if resp.status_code == 200:
                items = resp.json().get("result", {}).get("data", {}).get("feed", {}).get("list", [])
                if not items: break # 到底了
                
                for item in items:
                    if len(telegraphs) >= count: break
                    rich_text = item.get("rich_text", "")
                    if not rich_text: continue
                    
                    title = ""
                    content = rich_text
                    if "】" in rich_text and rich_text.startswith("【"):
                        parts = rich_text.split("】", 1)
                        title = parts[0].replace("【", "").strip()
                        content = parts[1].strip() if len(parts) > 1 else title
                    else:
                        title = content[:60] + "..."
                    
                    full_text = title + content
                    # 漏斗清洗
                    if any(w in full_text for w in noise_words): continue
                    if any(w in full_text for w in overseas_words):
                        if overseas_current >= overseas_limit: continue
                        overseas_current += 1

                    time_str = item.get("create_time", "")
                    pub_time = time_str.split(" ")[1][:5] if " " in time_str else time_str
                    
                    telegraphs.append({"time": pub_time, "title": title, "content": content, "important": False, "source": "新浪财经"})
    except Exception as e:
        print(f"[报错诊断] 新浪原生接口多页抓取失败: {e}")

    # 2. 东方财富原生底层补底 (同样支持翻页)
    if len(telegraphs) < count:
        try:
            for page in range(1, 6):
                if len(telegraphs) >= count: break
                url = f"https://fast-infoapi.eastmoney.com/api/news/list?client=web&biz=live&pageSize=100&pageIndex={page}"
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(url, headers=headers, timeout=5, verify=False)
                
                if resp.status_code == 200:
                    items = resp.json().get("data", [])
                    if not items: break
                    
                    for item in items:
                        if len(telegraphs) >= count: break
                        t_title = item.get("title", "")
                        content = item.get("digest", "") or t_title
                        full_text = t_title + content
                        
                        if not t_title or any(t_title in t["title"] for t in telegraphs): continue
                        if any(w in full_text for w in noise_words): continue
                        if any(w in full_text for w in overseas_words):
                            if overseas_current >= overseas_limit: continue
                            overseas_current += 1

                        time_str = item.get("showTime", "")
                        pub_time = time_str.split(" ")[1][:5] if " " in time_str else time_str
                        telegraphs.append({"time": pub_time, "title": t_title, "content": content, "important": False, "source": "东方财富"})
        except Exception as e:
            print(f"[报错诊断] 东财原生接口多页抓取失败: {e}")

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