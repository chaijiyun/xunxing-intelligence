"""
📰 资讯中心 - 实时采集与AI分析
"""
import streamlit as st
import pandas as pd
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_fetcher import get_cls_telegraph
from utils.ai_analyzer import analyze_news_batch, analyze_single_news

st.set_page_config(page_title="资讯中心", page_icon="📰", layout="wide")
st.title("📰 资讯中心")
st.caption("实时财经资讯采集 + AI 结构化分析")
st.divider()

# 控制面板
col1, col2 = st.columns([3, 1])
with col1:
    news_count = st.slider("采集数量", 10, 80, 40, step=10)
with col2:
    st.write("")
    fetch_btn = st.button("🔄 采集资讯", type="primary", use_container_width=True)

# Session state
if "raw_news" not in st.session_state:
    st.session_state.raw_news = []
if "analyzed_news" not in st.session_state:
    st.session_state.analyzed_news = []

# 采集
if fetch_btn or not st.session_state.raw_news:
    with st.spinner("📡 正在采集财联社电报..."):
        news = get_cls_telegraph(news_count)
        st.session_state.raw_news = news
        st.session_state.analyzed_news = []
    if news:
        st.success(f"✅ 采集到 {len(news)} 条资讯")
    else:
        st.warning("未能采集到资讯，请稍后重试")

raw_news = st.session_state.raw_news

if not raw_news:
    st.info("点击「采集资讯」按钮开始")
    st.stop()

# AI分析
st.divider()
col_a1, col_a2 = st.columns([3, 1])
with col_a1:
    st.subheader("🤖 AI 结构化分析")
with col_a2:
    analyze_btn = st.button("⚡ 运行AI分析", type="primary", use_container_width=True)

if analyze_btn:
    with st.spinner("🤖 DeepSeek 正在分析..."):
        analyzed = analyze_news_batch(raw_news)
        st.session_state.analyzed_news = analyzed
        st.success(f"✅ 完成 {len(analyzed)} 条分析")

analyzed = st.session_state.analyzed_news

# ============================================================
# 展示
# ============================================================
if analyzed:
    st.divider()
    st.subheader("📊 分析统计")

    cats = {}
    sents = []
    all_secs = {}
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
    sentiment_label = "偏多🟢" if avg_s > 0.1 else ("偏空🔴" if avg_s < -0.1 else "中性⚪")
    m2.metric("整体情绪", f"{avg_s:.2f}", sentiment_label)
    m3.metric("利多", f"{pos_n}条")
    m4.metric("利空", f"{neg_n}条")

    # 分类 & 行业
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

    # 筛选
    filter_cat = st.multiselect("按分类筛选", list(cats.keys()), default=list(cats.keys()))
    sort_opt = st.radio("排序", ["时间", "影响等级↓", "情感↓"], horizontal=True)

    filtered = [item for item in analyzed
                if item.get("analysis", {}).get("category", "其他") in filter_cat]

    if sort_opt == "影响等级↓":
        filtered.sort(key=lambda x: x.get("analysis", {}).get("impact", 0), reverse=True)
    elif sort_opt == "情感↓":
        filtered.sort(key=lambda x: x.get("analysis", {}).get("sentiment", 0), reverse=True)

    for i, item in enumerate(filtered):
        a = item.get("analysis", {})
        s = a.get("sentiment", 0)
        color = "#00D26A" if s > 0.2 else ("#FF4757" if s < -0.2 else "#636e72")
        emoji = "🟢" if s > 0.2 else ("🔴" if s < -0.2 else "⚪")
        sectors_str = " ".join(f"`{sec}`" for sec in a.get("sectors", []))

        st.markdown(
            f"**{item.get('time','')}** · {a.get('category','')} · "
            f"{emoji} {s:+.2f} · {'⭐'*a.get('impact',1)}"
        )
        st.markdown(f"> {item.get('title','')}")
        if sectors_str:
            st.caption(f"关联行业: {sectors_str}")

        with st.expander("详情 & 深度分析", expanded=False):
            st.markdown(item.get("content", "")[:500])
            if a.get("summary"):
                st.info(f"AI摘要: {a['summary']}")
            if st.button(f"🔍 深度分析", key=f"d_{i}"):
                with st.spinner("分析中..."):
                    result = analyze_single_news(f"{item.get('title','')}\n{item.get('content','')}")
                    st.markdown(result)

        st.markdown("---")

else:
    # 未分析，展示原始
    st.subheader("📋 原始资讯")
    st.info("💡 点击「运行AI分析」启用结构化分析")

    for item in raw_news[:30]:
        imp = "🔴 " if item.get("important") else ""
        st.markdown(f"**{item.get('time','')}** · {item.get('source','')} · {imp}{item.get('title','')}")
