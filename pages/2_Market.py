"""
📊 市场总览 - 行情 · 板块 · 资金 · 宏观
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
st.title("📊 市场总览")
st.caption("全市场行情 · 板块资金 · 宏观数据 · 市场风格")

if st.button("🔄 刷新", type="primary"):
    st.cache_data.clear()
    st.rerun()

st.divider()

# ============================================================
# 1. 指数行情
# ============================================================
st.subheader("📈 主要指数")

with st.spinner("加载指数..."):
    idx_df = get_major_indices()

if idx_df is not None and not idx_df.empty and "error" not in idx_df.columns:
    cols = st.columns(min(len(idx_df), 7))
    for i, (_, row) in enumerate(idx_df.iterrows()):
        if i >= len(cols):
            break
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
else:
    st.info("指数数据加载中...")

# ============================================================
# 2. 涨跌概况
# ============================================================
st.divider()
st.subheader("🎯 全A涨跌")

with st.spinner("统计中..."):
    ov = get_market_overview()

if ov and "error" not in ov:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("上涨", ov.get("上涨", 0), f"{ov.get('上涨占比',0)}%")
    c2.metric("下跌", ov.get("下跌", 0))
    c3.metric("平盘", ov.get("平盘", 0))
    c4.metric("涨停", ov.get("涨停", 0))
    c5.metric("跌停", ov.get("跌停", 0))
    c6.metric("成交额", f"{ov.get('总成交额亿',0):,.0f}亿")
else:
    st.info("涨跌数据加载中...")

# ============================================================
# 3. 市场风格
# ============================================================
st.divider()
st.subheader("🎭 市场风格（近5日）")

with st.spinner("计算风格..."):
    style = get_style_data()

if style:
    s1, s2, s3 = st.columns(3)
    s1.metric("风格偏好", style.get("偏好", "—"))
    s2.metric("沪深300", f"{style.get('沪深300_5日', '—')}%")
    s3.metric("中证1000", f"{style.get('中证1000_5日', '—')}%")
else:
    st.info("风格数据计算中...")

# ============================================================
# 4. 行业板块
# ============================================================
st.divider()
st.subheader("🏭 行业板块涨跌幅")

with st.spinner("加载行业板块..."):
    ind_df = get_industry_board()

if ind_df is not None and not ind_df.empty:
    show_cols = [c for c in ["板块名称", "涨跌幅", "总市值", "换手率", "上涨家数", "下跌家数"]
                 if c in ind_df.columns]
    if show_cols:
        st.dataframe(ind_df[show_cols].head(30), use_container_width=True, height=400)
    else:
        st.dataframe(ind_df.head(30), use_container_width=True, height=400)
else:
    st.info("行业数据加载中...")

# ============================================================
# 5. 概念板块
# ============================================================
st.divider()
st.subheader("🔥 概念板块 TOP 20")

with st.spinner("加载概念板块..."):
    con_df = get_concept_board()

if con_df is not None and not con_df.empty:
    show_cols = [c for c in ["板块名称", "涨跌幅", "总市值", "换手率", "上涨家数", "下跌家数"]
                 if c in con_df.columns]
    if show_cols:
        st.dataframe(con_df[show_cols].head(20), use_container_width=True, height=400)
    else:
        st.dataframe(con_df.head(20), use_container_width=True, height=400)
else:
    st.info("概念数据加载中...")

# ============================================================
# 6. 宏观数据
# ============================================================
st.divider()
st.subheader("🌐 宏观经济")

with st.spinner("加载宏观数据..."):
    macro = get_macro_data()

if macro:
    mcols = st.columns(len(macro))
    for i, (k, v) in enumerate(macro.items()):
        mcols[i].metric(k, str(v))
else:
    st.info("宏观数据加载中...")

# ============================================================
# 7. ETF
# ============================================================
st.divider()
st.subheader("📦 ETF 行情")

with st.spinner("加载ETF..."):
    etf_df = get_etf_list()

if etf_df is not None and not etf_df.empty:
    show_cols = [c for c in ["代码", "名称", "最新价", "涨跌幅", "成交额"]
                 if c in etf_df.columns]
    if show_cols:
        st.dataframe(etf_df[show_cols], use_container_width=True, height=400)
    else:
        st.dataframe(etf_df, use_container_width=True, height=400)
else:
    st.info("ETF数据加载中...")

# 页脚
st.divider()
st.caption(f"更新时间: {datetime.now().strftime('%H:%M:%S')} · 数据来源: AKShare · 仅供参考")
