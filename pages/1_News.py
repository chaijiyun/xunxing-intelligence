"""
📰 资讯雷达 V4 - Tushare PRO 8源并行 + AI 分析
================================================================
"""
import streamlit as st
import pandas as pd
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_fetcher import get_all_news, _tushare_available, TUSHARE_NEWS_SOURCES
from utils.ai_analyzer import analyze_news_batch, analyze_single_news, summarize_market_threads

st.set_page_config(page_title="资讯雷达", page_icon="📰", layout="wide")

# 登录检查
if not st.session_state.get("authenticated"):
    st.warning("请先登录")
    st.page_link("app.py", label="🔐 返回登录", icon="🏠")
    st.stop()

st.title("📰 资讯雷达")

if _tushare_available():
    src_names = [f"{name}" for _, name, _, _ in TUSHARE_NEWS_SOURCES]
    st.caption(f"Tushare PRO 8源: {' · '.join(src_names)} + 新闻联播")
else:
    st.warning("⚠️ Tushare PRO 未配置，仅使用新浪快讯 (降级模式)")
st.divider()

# 控制面板
col1, col2 = st.columns([3, 1])
with col1:
    news_count = st.slider("采集目标数量 (去重后)", 50, 300, 150, step=10,
                           help="从8个源并行采集，去重过滤后输出高价值资讯")
with col2:
    st.write("")
    fetch_btn = st.button("🔄 采集资讯", type="primary", use_container_width=True)

if "raw_news" not in st.session_state:
    st.session_state.raw_news = []
if "analyzed_news" not in st.session_state:
    st.session_state.analyzed_news = []

# 采集
if fetch_btn or not st.session_state.raw_news:
    with st.spinner(f"📡 正在从 8 个新闻源并行采集并去重过滤..."):
        news = get_all_news(tushare_count=news_count)
        st.session_state.raw_news = news
        st.session_state.analyzed_news = []
    if news:
        src_counts = {}
        cat_counts = {}
        important_count = 0
        for n in news:
            src = n.get("source", "未知")
            src_counts[src] = src_counts.get(src, 0) + 1
            cat = n.get("category", "未知")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            if n.get("important"):
                important_count += 1

        st.success(f"✅ 采集完成 {len(news)} 条高价值资讯 (重要 {important_count} 条)")

        with st.container(border=True):
            src_cols = st.columns(min(len(src_counts), 6))
            for i, (src, cnt) in enumerate(sorted(src_counts.items(), key=lambda x: -x[1])):
                src_cols[i % len(src_cols)].metric(src, f"{cnt}条")
    else:
        st.warning("未采集到资讯，请检查 Tushare Token 配置")

raw_news = st.session_state.raw_news
if not raw_news:
    st.info("点击「采集资讯」按钮开始")
    st.stop()

# ============================================================
# AI 分析面板
# ============================================================
st.divider()
col_a1, col_a2, col_a3 = st.columns([2, 1, 1])
with col_a1:
    st.subheader("🤖 AI 分析引擎")
with col_a2:
    analyze_btn = st.button("⚡ 逐条结构化分析", type="secondary", use_container_width=True)
with col_a3:
    summarize_btn = st.button("🔥 一键提炼核心主线", type="primary", use_container_width=True)

if summarize_btn:
    with st.spinner(f"🤖 DeepSeek 正在分析 {len(raw_news)} 条多源资讯，提炼投资主线..."):
        threads_report = summarize_market_threads(raw_news)
        st.markdown("""
        <div style="padding:16px 20px; border-radius:10px;
        background: linear-gradient(135deg, rgba(255,107,53,0.1), rgba(69,183,209,0.05));
        border: 1px solid rgba(255,107,53,0.2); margin-bottom:20px;">
        """, unsafe_allow_html=True)
        st.markdown(threads_report)
        st.markdown("</div>", unsafe_allow_html=True)

if analyze_btn:
    with st.spinner(f"🤖 DeepSeek 正在逐条分析 {len(raw_news)} 条资讯..."):
        analyzed = analyze_news_batch(raw_news)
        st.session_state.analyzed_news = analyzed
        st.success(f"✅ 完成 {len(analyzed)} 条结构化分析")

analyzed = st.session_state.analyzed_news

# ============================================================
# 展示
# ============================================================
if analyzed:
    st.divider()
    st.subheader("📊 分析统计")

    cats, sents, all_secs = {}, [], {}
    for item in analyzed:
        a = item.get("analysis", {})
        cat = a.get("category", "其他")
        cats[cat] = cats.get(cat, 0) + 1
        sents.append(a.get("sentiment", 0))
        for s in a.get("sectors", []):
            all_secs[s] = all_secs.get(s, 0) + 1

    avg_s = sum(sents) / len(sents) if sents else 0
    pos_n = sum(1 for s in sents if s > 0.1)
    neg_n = sum(1 for s in sents if s < -0.1)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("资讯总数", f"{len(analyzed)}")
    label = "偏多🟢" if avg_s > 0.1 else ("偏空🔴" if avg_s < -0.1 else "中性⚪")
    m2.metric("整体情绪", f"{avg_s:.2f}", label)
    m3.metric("利多", f"{pos_n}条")
    m4.metric("利空", f"{neg_n}条")

    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown("**分类分布**")
        if cats:
            st.bar_chart(pd.DataFrame({"数量": cats}).sort_values("数量", ascending=False), height=200)
    with cc2:
        st.markdown("**热门行业**")
        if all_secs:
            st.bar_chart(pd.DataFrame({"提及": all_secs}).sort_values("提及", ascending=False), height=200)

    st.divider()
    st.subheader("📋 资讯列表")

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        filter_cat = st.multiselect("按分类筛选", list(cats.keys()), default=list(cats.keys()))
    with col_f2:
        all_sources = list(set(item.get("source", "") for item in analyzed))
        filter_src = st.multiselect("按来源筛选", all_sources, default=all_sources)
    with col_f3:
        sort_opt = st.radio("排序", ["时间", "影响↓", "情感↓"], horizontal=True)

    filtered = [item for item in analyzed
                if item.get("analysis", {}).get("category", "其他") in filter_cat
                and item.get("source", "") in filter_src]

    if sort_opt == "影响↓":
        filtered.sort(key=lambda x: x.get("analysis", {}).get("impact", 0), reverse=True)
    elif sort_opt == "情感↓":
        filtered.sort(key=lambda x: x.get("analysis", {}).get("sentiment", 0), reverse=True)

    for i, item in enumerate(filtered):
        a = item.get("analysis", {})
        s = a.get("sentiment", 0)
        emoji = "🟢" if s > 0.2 else ("🔴" if s < -0.2 else "⚪")
        sectors_str = " ".join(f"`{sec}`" for sec in a.get("sectors", []))
        src = item.get("source", "")
        tier = item.get("tier", "")
        tier_badge = {"T0": "🏛️", "T1": "🔷", "T2": "🔹", "T3": "▫️"}.get(tier, "")

        st.markdown(f"**{item.get('time','')}** · {tier_badge}**[{src}]** · {a.get('category','')} · {emoji} {s:+.2f} · {'⭐'*a.get('impact',1)}")
        st.markdown(f"> {item.get('title','')}")
        if sectors_str:
            st.caption(f"关联行业: {sectors_str}")

        with st.expander("详情 & 深度分析", expanded=False):
            st.markdown(item.get("content", "")[:500])
            if a.get("summary"):
                st.info(f"AI摘要: {a['summary']}")
            if st.button(f"🔍 FOF视角深度分析", key=f"d_{i}"):
                with st.spinner("分析中..."):
                    result = analyze_single_news(f"{item.get('title','')}\n{item.get('content','')}")
                    st.markdown(result)
        st.markdown("---")

else:
    st.subheader("📋 原始资讯")
    st.info("💡 点击「🔥 一键提炼核心主线」或「⚡ 逐条结构化分析」启用 AI 引擎")

    cat_groups = {}
    for item in raw_news:
        cat = item.get("category", "综合财经")
        if cat not in cat_groups:
            cat_groups[cat] = []
        cat_groups[cat].append(item)

    for cat, items in cat_groups.items():
        with st.expander(f"📂 {cat} ({len(items)}条)", expanded=(cat in ("宏观政策", "行业产业"))):
            for item in items:
                src = item.get("source", "")
                important = "⭐ " if item.get("important") else ""
                tier = item.get("tier", "")
                tier_badge = {"T0": "🏛️", "T1": "🔷", "T2": "🔹", "T3": "▫️"}.get(tier, "")
                st.markdown(f"**{item.get('time','')}** · {tier_badge}**[{src}]** · {important}{item.get('title','')}")
