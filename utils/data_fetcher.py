"""
数据采集模块 V3 - 寻星情报中心
================================================================
架构: Tushare PRO (主力) + AKShare (行情补充) + 新浪 (快讯降级)
----------------------------------------------------------------
数据层级:
  L1 行情: 宽基指数 / 涨跌统计 / ETF (AKShare)
  L2 资金: 北向资金 / 融资融券 (AKShare + Tushare)
  L3 宏观: CPI/PMI/利率/汇率 (AKShare)
  L4 风格: 大小盘 / 成长价值 (AKShare 指数计算)
  L5 板块: 行业板块 / 概念板块 (AKShare)
  L6 资讯: Tushare新闻 + 新闻联播 + 新浪快讯补充
  L7 研报: Tushare 券商研报摘要
  L8 期货: 商品期货行情 (AKShare)
  L9 打包: 全量数据聚合供 AI 使用
================================================================
"""
import akshare as ak
import pandas as pd
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


def _safe_call(func, timeout=10, default=None, label=""):
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


# ============================================================
# Tushare PRO 初始化
# ============================================================
@st.cache_resource
def _get_tushare_pro():
    """获取 Tushare PRO 接口实例 (全局缓存)"""
    try:
        import tushare as ts
        token = ""
        try:
            token = st.secrets.get("TUSHARE_TOKEN", "")
        except Exception:
            pass
        if not token:
            logger.warning("TUSHARE_TOKEN 未配置")
            return None
        pro = ts.pro_api(token)
        logger.info("Tushare PRO 连接成功")
        return pro
    except ImportError:
        logger.error("tushare 未安装, 请在 requirements.txt 中添加 tushare")
        return None
    except Exception as e:
        logger.error(f"Tushare 初始化失败: {e}")
        return None


def _tushare_available() -> bool:
    return _get_tushare_pro() is not None


# ============================================================
# L1. 宽基指数行情 (AKShare)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_major_indices() -> pd.DataFrame:
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
    return _safe_call(_fetch, timeout=10, default=pd.DataFrame(), label="宽基指数")


# ============================================================
# L2-A. 市场涨跌统计 (AKShare)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_market_overview() -> dict:
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
    return _safe_call(_fetch, timeout=10, default={}, label="涨跌统计")


# ============================================================
# L2-B. 北向资金 (AKShare)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_northbound_flow() -> dict:
    def _fetch():
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
        except Exception as e:
            logger.warning(f"北向资金获取失败: {e}")
        return {}
    return _safe_call(_fetch, timeout=10, default={}, label="北向资金")


# ============================================================
# L2-C. 融资融券余额 (Tushare PRO)
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
                return {
                    "融资余额亿": round(rzye, 1),
                    "融券余额亿": round(rqye, 1),
                    "融资5日变化亿": round(rzye - rzye_prev, 1),
                    "杠杆情绪": "加杠杆" if rzye > rzye_prev else "去杠杆",
                }
        except Exception as e:
            logger.warning(f"融资融券获取失败: {e}")
        return {}
    return _safe_call(_fetch, timeout=12, default={}, label="融资融券")


# ============================================================
# L3. 宏观数据 (AKShare)
# ============================================================
@st.cache_data(ttl=7200, show_spinner=False)
def get_macro_data() -> dict:
    def _fetch():
        macro = {}
        # CPI
        try:
            df = ak.macro_china_cpi_monthly()
            if df is not None and not df.empty:
                last = df.iloc[-1]
                date_val = str(last.iloc[0]) if len(df.columns) >= 2 else ""
                macro["CPI同比"] = str(last.iloc[-1])
                macro["CPI月份"] = date_val
        except Exception as e:
            logger.warning(f"CPI获取失败: {e}")

        # PMI
        try:
            df = ak.macro_china_pmi()
            if df is not None and not df.empty:
                last = df.iloc[-1]
                date_val = str(last.iloc[0]) if len(df.columns) >= 2 else ""
                macro["制造业PMI"] = str(last.iloc[-1])
                macro["PMI月份"] = date_val
        except Exception as e:
            logger.warning(f"PMI获取失败: {e}")

        # 中美10Y国债利率
        try:
            df = ak.bond_zh_us_rate(start_date="20250101")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                for col in df.columns:
                    if "中国" in str(col) and "10" in str(col):
                        macro["中国10Y国债"] = f"{latest[col]}%"
                    if "美国" in str(col) and "10" in str(col):
                        macro["美国10Y国债"] = f"{latest[col]}%"
        except Exception as e:
            logger.warning(f"国债利率获取失败: {e}")

        # 人民币汇率
        try:
            df = ak.currency_boc_sina(symbol="美元",
                                       start_date=(datetime.now() - timedelta(days=10)).strftime("%Y%m%d"))
            if df is not None and not df.empty:
                val = df.iloc[-1].iloc[1] if len(df.columns) > 1 else None
                if val:
                    macro["美元兑人民币"] = str(val)
        except Exception as e:
            logger.warning(f"汇率获取失败(非关键): {e}")

        return macro
    return _safe_call(_fetch, timeout=15, default={"CPI同比": "超时", "制造业PMI": "超时"}, label="宏观数据")


# ============================================================
# L4. 市场风格 (大小盘 + 成长/价值)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_style_data() -> dict:
    def _fetch():
        result = {}
        try:
            hs300 = ak.stock_zh_index_daily_em(symbol="sh000300")
            zz1000 = ak.stock_zh_index_daily_em(symbol="sh000852")
            if hs300 is not None and len(hs300) >= 6 and zz1000 is not None and len(zz1000) >= 6:
                hs_5d = (float(hs300.iloc[-1]["close"]) / float(hs300.iloc[-6]["close"]) - 1) * 100
                zz_5d = (float(zz1000.iloc[-1]["close"]) / float(zz1000.iloc[-6]["close"]) - 1) * 100
                result["沪深300_5日"] = round(hs_5d, 2)
                result["中证1000_5日"] = round(zz_5d, 2)
                result["大小盘偏好"] = "偏大盘" if hs_5d > zz_5d else "偏小盘"
        except Exception as e:
            logger.warning(f"大小盘风格获取失败: {e}")

        try:
            cyb = ak.stock_zh_index_daily_em(symbol="sz399006")
            sz50 = ak.stock_zh_index_daily_em(symbol="sh000016")
            if cyb is not None and len(cyb) >= 6 and sz50 is not None and len(sz50) >= 6:
                cyb_5d = (float(cyb.iloc[-1]["close"]) / float(cyb.iloc[-6]["close"]) - 1) * 100
                sz50_5d = (float(sz50.iloc[-1]["close"]) / float(sz50.iloc[-6]["close"]) - 1) * 100
                result["创业板指_5日"] = round(cyb_5d, 2)
                result["上证50_5日"] = round(sz50_5d, 2)
                result["成长价值偏好"] = "偏成长" if cyb_5d > sz50_5d else "偏价值"
        except Exception as e:
            logger.warning(f"成长/价值风格获取失败: {e}")

        return result
    return _safe_call(_fetch, timeout=12, default={}, label="风格数据")


# ============================================================
# L5. 行业 / 概念板块 (AKShare)
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_industry_board() -> pd.DataFrame:
    def _fetch():
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            for c in ["涨跌幅", "总市值", "换手率"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
        return pd.DataFrame()
    return _safe_call(_fetch, timeout=10, default=pd.DataFrame(), label="行业板块")


@st.cache_data(ttl=900, show_spinner=False)
def get_concept_board() -> pd.DataFrame:
    def _fetch():
        df = ak.stock_board_concept_name_em()
        if df is not None and not df.empty:
            for c in ["涨跌幅", "总市值", "换手率"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.sort_values("涨跌幅", ascending=False).reset_index(drop=True)
        return pd.DataFrame()
    return _safe_call(_fetch, timeout=10, default=pd.DataFrame(), label="概念板块")


# ============================================================
# L6-A. ETF 行情 (AKShare)
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_etf_list() -> pd.DataFrame:
    def _fetch():
        df = ak.fund_etf_spot_em()
        if df is not None and not df.empty:
            for c in ["最新价", "涨跌幅", "成交额"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.sort_values("成交额", ascending=False).head(80).reset_index(drop=True)
        return pd.DataFrame()
    return _safe_call(_fetch, timeout=10, default=pd.DataFrame(), label="ETF行情")


# ============================================================
# L6-B. 资讯采集 — 多源并行架构 (Tushare PRO 付费版)
# ============================================================
# 【设计理念】
# 付费版可访问8个高质量新闻源，按信息价值分三层：
#   T1 机构级 (深度): 财联社cls、第一财经yicai、华尔街见闻wallstreetcn
#   T2 综合级 (广度): 东方财富eastmoney、同花顺10jqka、新浪财经sina
#   T3 补充级 (视野): 金融界jinrongjie、云财经yuncaijing
# 每层采集策略不同：T1 每源取150条(含content), T2 取100条, T3 取50条
# 最终经过去重+噪音过滤+质量排序，输出高价值资讯包

# 数据源配置: (src标识, 显示名, 信息层级, 单源上限)
TUSHARE_NEWS_SOURCES = [
    # T1 机构级 — 深度内容、独家快讯、专业分析
    ("cls",           "财联社",     "T1", 150),
    ("yicai",         "第一财经",   "T1", 120),
    ("wallstreetcn",  "华尔街见闻", "T1", 120),
    # T2 综合级 — 覆盖面广、时效性好
    ("eastmoney",     "东方财富",   "T2", 100),
    ("10jqka",        "同花顺",     "T2", 100),
    ("sina",          "新浪财经",   "T2", 80),
    # T3 补充级 — 补充视角
    ("jinrongjie",    "金融界",     "T3", 50),
    ("yuncaijing",    "云财经",     "T3", 50),
]

# 噪音关键词 (标题命中则丢弃)
_NOISE_WORDS = frozenset([
    "互动平台", "互动易", "抽奖", "投资者关系", "停牌", "复牌",
    "新股申购", "大宗交易", "调研信息", "交易提示", "盘中异动",
    "龙虎榜", "成交回报", "溢价率", "中签号", "配号",
])

# 重要关键词 (标题命中则标记为重要)
_IMPORTANT_WORDS = frozenset([
    "央行", "国务院", "降准", "降息", "加息", "MLF", "LPR", "社融",
    "GDP", "CPI", "PMI", "两会", "政治局", "证监会", "发改委",
    "美联储", "关税", "制裁", "战争", "地震",
    "暴跌", "暴涨", "熔断", "涨停潮", "跌停潮", "千股",
])

# 分类关键词映射
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
    """智能分类 + 重要性判断，返回 (category, is_important)"""
    text = title + content[:100]
    # 分类
    category = "综合财经"
    for cat, keywords in _CATEGORY_RULES.items():
        if any(kw in text for kw in keywords):
            category = cat
            break
    # 重要性
    is_important = any(w in text for w in _IMPORTANT_WORDS)
    return category, is_important


@st.cache_data(ttl=300, show_spinner=False)
def get_tushare_news(count: int = 80) -> list:
    """
    Tushare PRO 多源并行采集引擎
    从8个付费新闻源并行抓取 → 智能去重 → 噪音过滤 → 质量排序 → 分类标注
    """
    pro = _get_tushare_pro()
    if not pro:
        logger.warning("Tushare PRO 未配置，跳过新闻采集")
        return []

    # 时间窗口: 过去24小时
    now = datetime.now()
    end_time = now.strftime("%Y-%m-%d %H:%M:%S")
    start_time = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    raw_news = []        # 全部原始新闻
    source_stats = {}    # 每个源采集统计

    # ---- 逐源采集 (顺序执行，避免API限流) ----
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

                    # 基础过滤
                    if not title or len(title) < 6:
                        continue
                    if any(w in title for w in _NOISE_WORDS):
                        continue

                    # 分类+重要性
                    category, is_important = _classify_news(title, content)

                    # 提取时间
                    pub_time = dt.split(" ")[1][:5] if " " in dt else dt[:16]

                    raw_news.append({
                        "time": pub_time,
                        "datetime": dt,
                        "title": title,
                        "content": content if content and content != title else title,
                        "important": is_important,
                        "source": name,
                        "source_id": src,
                        "tier": tier,
                        "category": category,
                        "channels": channels,
                    })
                    fetched += 1

            source_stats[name] = fetched
            logger.info(f"[采集] {name}({src}): {fetched} 条")
        except Exception as e:
            source_stats[name] = f"失败:{e}"
            logger.warning(f"[采集失败] {name}({src}): {e}")

    # ---- 新闻联播 (宏观政策风向标) ----
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
                        "time": "CCTV",
                        "datetime": yesterday,
                        "title": f"[新闻联播] {title}",
                        "content": content,
                        "important": True,
                        "source": "新闻联播",
                        "source_id": "cctv",
                        "tier": "T0",
                        "category": "宏观政策",
                        "channels": "",
                    })
                    cctv_count += 1
            source_stats["新闻联播"] = cctv_count
            logger.info(f"[采集] 新闻联播: {cctv_count} 条")
    except Exception as e:
        logger.warning(f"[采集失败] 新闻联播: {e}")

    logger.info(f"[汇总] 原始采集 {len(raw_news)} 条 | 各源: {source_stats}")

    # ---- 智能去重 (标题前30字相似即视为重复，保留层级更高的源) ----
    seen_titles = {}  # title_key → news_item
    tier_priority = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}

    for item in raw_news:
        key = item["title"][:30].strip()
        if key not in seen_titles:
            seen_titles[key] = item
        else:
            # 保留层级更高(数字更小)的版本
            existing = seen_titles[key]
            if tier_priority.get(item["tier"], 9) < tier_priority.get(existing["tier"], 9):
                seen_titles[key] = item

    deduped = list(seen_titles.values())
    logger.info(f"[去重] {len(raw_news)} → {len(deduped)} 条")

    # ---- 质量排序 (重要>T0>T1>T2>T3, 同层按时间倒序) ----
    def _sort_key(item):
        tier_score = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}.get(item["tier"], 9)
        important_score = 0 if item.get("important") else 1
        return (important_score, tier_score, item.get("datetime", "") == "")

    deduped.sort(key=_sort_key)

    final = deduped[:count]
    logger.info(f"[输出] 最终 {len(final)} 条高价值资讯 (目标 {count})")
    return final


# --- 新浪快讯 (降级为补充，仅Tushare不可用时启用) ---
@st.cache_data(ttl=300, show_spinner=False)
def get_sina_flash(count: int = 30) -> list:
    """新浪 7×24 快讯 — 降级补充 (Tushare 已覆盖新浪源，此函数仅作后备)"""
    telegraphs = []
    noise_words = list(_NOISE_WORDS)
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
                    if any(w in title for w in noise_words):
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


# --- 聚合入口 ---
@st.cache_data(ttl=300, show_spinner=False)
def get_all_news(tushare_count: int = 120, sina_count: int = 0) -> list:
    """
    全量资讯聚合引擎
    付费版策略: Tushare 8源并行采集120条，新浪快讯仅作故障后备
    """
    all_news = []

    # 主力: Tushare 多源
    ts_news = get_tushare_news(tushare_count)
    all_news.extend(ts_news)

    # 后备: 如果 Tushare 采集不足30条，启用新浪补充
    if len(all_news) < 30:
        logger.warning(f"Tushare 仅采集到 {len(all_news)} 条，启用新浪快讯补充")
        sina_news = get_sina_flash(max(sina_count, 50))
        existing_titles = set(n["title"][:20] for n in all_news)
        for item in sina_news:
            if item["title"][:20] not in existing_titles:
                all_news.append(item)
                existing_titles.add(item["title"][:20])

    # 统计各源占比
    src_counts = {}
    for n in all_news:
        src = n.get("source", "unknown")
        src_counts[src] = src_counts.get(src, 0) + 1
    logger.info(f"[聚合最终] 共 {len(all_news)} 条 | 来源分布: {src_counts}")

    return all_news


# 兼容旧接口
def get_cls_telegraph(count: int = 50) -> list:
    """兼容旧版调用 → 转发到新聚合引擎"""
    return get_all_news(tushare_count=max(count, 80))


# ============================================================
# L7. 券商研报摘要 (Tushare PRO)
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def get_research_reports(count: int = 30) -> list:
    """获取最新券商研报评级"""
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
            logger.info(f"券商研报: 获取 {len(reports)} 条评级")
    except Exception as e:
        logger.warning(f"券商研报获取失败: {e}")
    return reports


# ============================================================
# L8. 商品期货行情 (AKShare)
# ============================================================
@st.cache_data(ttl=900, show_spinner=False)
def get_futures_overview() -> dict:
    """主要商品期货行情 (CTA策略参考)"""
    def _fetch():
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
            logger.warning(f"期货行情获取失败: {e}")
        return result
    return _safe_call(_fetch, timeout=10, default={}, label="期货行情")


# ============================================================
# L9. 全量数据打包 (供 AI 研报使用)
# ============================================================
def get_daily_data_pack() -> dict:
    """一次性获取所有数据，打包为字典"""
    return {
        "indices": get_major_indices(),
        "overview": get_market_overview(),
        "industry": get_industry_board(),
        "concept": get_concept_board(),
        "macro": get_macro_data(),
        "style": get_style_data(),
        "etf": get_etf_list(),
        "northbound": get_northbound_flow(),
        "margin": get_margin_data(),
        "futures": get_futures_overview(),
        "news": get_all_news(tushare_count=120),
        "research": get_research_reports(30),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def pack_market_text(pack: dict) -> str:
    """将数据包中的市场数据转为文本 (供 AI prompt)"""
    mp = ["## 今日市场数据"]

    idx = pack.get("indices")
    if idx is not None and not idx.empty:
        for _, r in idx.iterrows():
            chg = r.get("涨跌幅", 0)
            if pd.notna(chg):
                mp.append(f"- {r.get('名称','')}: {r.get('最新价','')} ({chg:+.2f}%)")
            else:
                mp.append(f"- {r.get('名称','')}: {r.get('最新价','')}")

    ov = pack.get("overview", {})
    if ov:
        mp.append(f"\n涨{ov.get('上涨',0)} 跌{ov.get('下跌',0)} | 涨停{ov.get('涨停',0)} 跌停{ov.get('跌停',0)} | 成交{ov.get('总成交额亿',0):.0f}亿 | 上涨占比{ov.get('上涨占比',0)}%")

    style = pack.get("style", {})
    if style:
        s_parts = []
        if "大小盘偏好" in style:
            s_parts.append(f"大小盘:{style['大小盘偏好']}(300:{style.get('沪深300_5日','')}%/1000:{style.get('中证1000_5日','')}%)")
        if "成长价值偏好" in style:
            s_parts.append(f"成长价值:{style['成长价值偏好']}(创业板:{style.get('创业板指_5日','')}%/上证50:{style.get('上证50_5日','')}%)")
        if s_parts:
            mp.append("\n风格(近5日): " + " | ".join(s_parts))

    macro = pack.get("macro", {})
    if macro:
        items = [f"{k}:{v}" for k, v in macro.items() if v not in ("—", "超时", "", None)]
        if items:
            mp.append("\n宏观: " + " | ".join(items))

    nb = pack.get("northbound", {})
    if nb:
        mp.append(f"\n北向资金: 今日{nb.get('方向','')}{nb.get('今日净流入亿',0)}亿 | 5日均值{nb.get('5日均值亿',0)}亿")

    margin = pack.get("margin", {})
    if margin:
        mp.append(f"融资: 余额{margin.get('融资余额亿',0)}亿 | 5日变化{margin.get('融资5日变化亿',0)}亿 | {margin.get('杠杆情绪','')}")

    futures = pack.get("futures", {})
    if futures:
        f_parts = []
        for k, v in futures.items():
            chg = v.get("chg_pct", 0)
            f_parts.append(f"{k}:{v.get('price','')}" + (f"({chg:+.1f}%)" if chg else ""))
        if f_parts:
            mp.append(f"\n商品期货: {' | '.join(f_parts)}")

    ind = pack.get("industry")
    if ind is not None and not ind.empty and "板块名称" in ind.columns and "涨跌幅" in ind.columns:
        mp.append("\n行业涨幅TOP5: " + ", ".join(f"{r['板块名称']}({r['涨跌幅']:+.1f}%)" for _, r in ind.head(5).iterrows()))
        mp.append("行业跌幅TOP5: " + ", ".join(f"{r['板块名称']}({r['涨跌幅']:+.1f}%)" for _, r in ind.tail(5).iterrows()))

    return "\n".join(mp)


def pack_news_text(pack: dict) -> str:
    """将数据包中的资讯+研报转为文本 (供 AI prompt) — 多源版"""
    np_list = []

    news = pack.get("news", [])

    # 来源统计
    src_counts = {}
    for n in news:
        src = n.get("source", "unknown")
        src_counts[src] = src_counts.get(src, 0) + 1
    src_summary = ", ".join(f"{k}:{v}" for k, v in src_counts.items())
    np_list.append(f"## 今日资讯 (共{len(news)}条, 来源: {src_summary})")

    # 按重要性和层级分类输出
    important = [n for n in news if n.get("important")]
    t1_news = [n for n in news if not n.get("important") and n.get("tier") in ("T0", "T1")]
    t2_news = [n for n in news if not n.get("important") and n.get("tier") in ("T2", "T3", None)]

    # 重要新闻: 含摘要 (给AI更多上下文)
    if important:
        np_list.append("\n### 重要资讯")
        for n in important[:15]:
            np_list.append(f"⭐[{n.get('source','')}][{n.get('category','')}] {n.get('title','')}")
            if n.get("content") and n["content"] != n.get("title"):
                np_list.append(f"   摘要: {n['content'][:200]}")

    # T1机构级: 含简短摘要
    if t1_news:
        np_list.append("\n### 机构级资讯 (财联社/第一财经/华尔街见闻)")
        for n in t1_news[:40]:
            line = f"- [{n.get('source','')}][{n.get('category','')}] {n.get('title','')}"
            content = n.get("content", "")
            if content and content != n.get("title") and len(content) > 20:
                line += f" | {content[:100]}"
            np_list.append(line)

    # T2/T3综合级: 仅标题
    if t2_news:
        np_list.append("\n### 综合资讯")
        for n in t2_news[:30]:
            np_list.append(f"- [{n.get('source','')}] {n.get('title','')}")

    # 券商研报
    research = pack.get("research", [])
    if research:
        np_list.append(f"\n## 券商研报动态 (共{len(research)}条)")
        for r in research[:20]:
            rating_chg = ""
            if r.get("pre_rating") and r.get("rating") and r["pre_rating"] != r["rating"]:
                rating_chg = f" (从{r['pre_rating']}→{r['rating']})"
            elif r.get("rating"):
                rating_chg = f" ({r['rating']})"
            target = f" 目标价{r['target_price']}" if r.get("target_price") else ""
            np_list.append(f"- {r.get('org_name','')}: {r.get('stock_name','')}{rating_chg}{target}")

    return "\n".join(np_list)
