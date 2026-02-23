"""
📊 市场总览 - 寻星 FOF 投研驾驶舱
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_fetcher import (
    get_major_indices, get_market_overview,
    get_industry_board, get_concept_board,
    get_macro_data, get_style_data, get_etf_list,
)

st.set_page_config(page_title="市场总览", page_icon="📊", layout="wide")
st.title("📊 寻星投研驾驶舱")
st.caption("自上而下观测：宏观环境 · 市场风格 · 宽基指数 · 结构性主线")

col_r1, col_r2 = st.columns([1, 5])
with col_r1:
    if st.button("🔄 刷新数据", type="primary"):
        st.cache_data.clear()
        st.rerun()
with col_r2:
    st.info("💡 FOF 视角：优先研判宏观与风格，再通过 ETF 和板块寻找结构性落地工具。")

st.divider()

# ============================================================
# 第一层：自上而下 - 宏观与全局风格 (CIO 关注核心)
# ============================================================
st.subheader("🧭 宏观环境与市场风格")
col_m1, col_m2 = st.columns([1, 1])

with col_m1:
    with st.spinner("加载宏观环境..."):
        macro = get_macro_data()
    if macro:
        # 使用容器让排版更紧凑
        with st.container(border=True):
            st.markdown("**🌐 关键宏观指标**")
            m_cols = st.columns(len(macro))
            for i, (k, v) in enumerate(macro.items()):
                m_cols[i].metric(k, str(v))
    else:
        st.warning("宏观数据暂不可用")

with col_m2:
    with st.spinner("计算风格暴露..."):
        style = get_style_data()
    if style:
        with st.container(border=True):
            st.markdown("**🎭 大小盘风格 (近5日)**")
            s1, s2, s3 = st.columns(3)
            s1.metric("风格偏好", style.get("偏好", "—"))
            s2.metric("沪深300", f"{style.get('沪深300_5日', '—')}%")
            s3.metric("中证1000", f"{style.get('中证1000_5日', '—')}%")
    else:
        st.warning("风格数据暂不可用")

# ============================================================
# 第二层：宽基指数与市场情绪
# ============================================================
st.subheader("📈 宽基指数与市场情绪")

with st.spinner("加载指数行情..."):
    idx_df = get_major_indices()

if idx_df is not None and not idx_df.empty and "error" not in idx_df.columns:
    cols = st.columns(min(len(idx_df), 7))
    for i, (_, row) in enumerate(idx_df.iterrows()):
        if i >= len(cols): break
        name = row.get("名称", "")
        price = row.get("最新价", 0)
        chg = row.get("涨跌幅", 0)
        with cols[i]:
            st.metric(
                name,
                f"{price:,.2f}" if pd.notna(price) else "—",
                f"{chg:+.2f}%" if pd.notna(chg) else "—",
                delta_color="normal" if (pd.notna(chg) and chg >= 0) else "inverse",
            )

with st.spinner("统计赚钱效应..."):
    ov = get_market_overview()

if ov and "error" not in ov:
    with st.container(border=True):
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("上涨家数", ov.get("上涨", 0), f"占比 {ov.get('上涨占比',0)}%")
        c2.metric("下跌家数", ov.get("下跌", 0))
        c3.metric("平盘家数", ov.get("平盘", 0))
        c4.metric("涨停", ov.get("涨停", 0))
        c5.metric("跌停", ov.get("跌停", 0))
        c6.metric("两市总成交额", f"{ov.get('总成交额亿',0):,.0f} 亿")

# ============================================================
# 第三层：结构性机会与底层工具 (使用 Tabs 优化前端渲染性能)
# ============================================================
st.divider()
st.subheader("🧩 结构性主线与工具箱")

# 使用选项卡（Tabs）可以避免长表格堆叠导致的页面滚动卡顿
tab1, tab2, tab3 = st.tabs(["📦 ETF 战术工具箱", "🏭 行业板块追踪", "🔥 概念题材热度"])

with tab1:
    with st.spinner("加载 ETF 工具箱..."):
        etf_df = get_etf_list()
    if etf_df is not None and not etf_df.empty:
        show_cols = [c for c in ["代码", "名称", "最新价", "涨跌幅", "成交额"] if c in etf_df.columns]
        st.dataframe(etf_df[show_cols] if show_cols else etf_df, width="stretch", height=350)

with tab2:
    with st.spinner("扫描行业异动..."):
        ind_df = get_industry_board()
    if ind_df is not None and not ind_df.empty:
        show_cols = [c for c in ["板块名称", "涨跌幅", "总市值", "换手率", "上涨家数", "下跌家数"] if c in ind_df.columns]
        st.dataframe(ind_df[show_cols].head(30) if show_cols else ind_df.head(30), width="stretch", height=350)

with tab3:
    with st.spinner("扫描概念热度..."):
        con_df = get_concept_board()
    if con_df is not None and not con_df.empty:
        show_cols = [c for c in ["板块名称", "涨跌幅", "总市值", "换手率", "上涨家数", "下跌家数"] if c in con_df.columns]
        st.dataframe(con_df[show_cols].head(20) if show_cols else con_df.head(20), width="stretch", height=350)

# 页脚
st.caption(f"更新时间: {datetime.now().strftime('%H:%M:%S')} · 数据来源: AKShare · 仅供参考")