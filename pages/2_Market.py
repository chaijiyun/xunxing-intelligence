"""
📊 FOF 投研驾驶舱 V3
================================================================
一屏呈现: 宏观 + 风格 + 指数 + 资金 + 期货 + 板块 + ETF + 研报
================================================================
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_fetcher import (
    get_major_indices, get_market_overview,
    get_industry_board, get_concept_board,
    get_macro_data, get_style_data, get_etf_list,
    get_northbound_flow, get_margin_data, get_futures_overview,
    get_research_reports, _tushare_available,
)

st.set_page_config(page_title="FOF 驾驶舱", page_icon="📊", layout="wide")
st.title("📊 寻星 FOF 投研驾驶舱")
st.caption("自上而下: 宏观 · 风格 · 资金 · 行情 · 期货 · 板块 · 研报")

col_r1, col_r2 = st.columns([1, 5])
with col_r1:
    if st.button("🔄 刷新", type="primary"):
        st.cache_data.clear()
        st.rerun()
with col_r2:
    tushare_status = "✅ Tushare PRO 已连接" if _tushare_available() else "⚠️ Tushare PRO 未配置"
    st.info(f"💡 FOF 视角: 宏观→风格→资金→行业→工具 | {tushare_status}")

st.divider()

# ============================================================
# 第一层: 宏观环境 + 市场风格
# ============================================================
st.subheader("🧭 宏观环境与市场风格")
col_m1, col_m2 = st.columns(2)

with col_m1:
    with st.spinner("加载宏观环境..."):
        macro = get_macro_data()
    if macro:
        with st.container(border=True):
            st.markdown("**🌐 关键宏观指标**")
            display_macro = {k: v for k, v in macro.items()
                           if k not in ("CPI月份", "PMI月份") and v not in ("—", "超时", "", None)}
            if display_macro:
                m_cols = st.columns(min(len(display_macro), 4))
                for i, (k, v) in enumerate(display_macro.items()):
                    m_cols[i % len(m_cols)].metric(k, str(v))
            cpi_month = macro.get("CPI月份", "")
            pmi_month = macro.get("PMI月份", "")
            if cpi_month or pmi_month:
                st.caption(f"数据月份: CPI {cpi_month} | PMI {pmi_month}")
    else:
        st.warning("宏观数据暂不可用")

with col_m2:
    with st.spinner("计算风格暴露..."):
        style = get_style_data()
    if style:
        with st.container(border=True):
            st.markdown("**🎭 市场风格 (近5日)**")
            s_cols = st.columns(4)
            s_cols[0].metric("大小盘", style.get("大小盘偏好", "—"))
            s_cols[1].metric("沪深300", f"{style.get('沪深300_5日', '—')}%")
            s_cols[2].metric("中证1000", f"{style.get('中证1000_5日', '—')}%")
            if "成长价值偏好" in style:
                s_cols[3].metric("成长/价值", style.get("成长价值偏好", "—"))
            if "创业板指_5日" in style:
                st.caption(f"创业板指 {style.get('创业板指_5日', '')}% | 上证50 {style.get('上证50_5日', '')}%")
    else:
        st.warning("风格数据暂不可用")

# ============================================================
# 第二层: 指数行情 + 涨跌情绪
# ============================================================
st.subheader("📈 宽基指数与市场情绪")

with st.spinner("加载指数行情..."):
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

with st.spinner("统计赚钱效应..."):
    ov = get_market_overview()

if ov and "error" not in ov:
    with st.container(border=True):
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("上涨家数", ov.get("上涨", 0), f"占比 {ov.get('上涨占比', 0)}%")
        c2.metric("下跌家数", ov.get("下跌", 0))
        c3.metric("平盘家数", ov.get("平盘", 0))
        c4.metric("涨停", ov.get("涨停", 0))
        c5.metric("跌停", ov.get("跌停", 0))
        c6.metric("两市成交额", f"{ov.get('总成交额亿', 0):,.0f} 亿")

# ============================================================
# 第三层: 资金流向 + 期货
# ============================================================
st.divider()
st.subheader("💰 资金流向与商品期货")

col_f1, col_f2, col_f3 = st.columns(3)

with col_f1:
    with st.spinner("加载北向资金..."):
        nb = get_northbound_flow()
    if nb:
        with st.container(border=True):
            st.markdown("**🌏 北向资金**")
            direction = nb.get("方向", "")
            color = "🟢" if "入" in direction else "🔴"
            st.metric(f"{color} {direction}", f"{nb.get('今日净流入亿', 0)} 亿")
            st.caption(f"5日均值: {nb.get('5日均值亿', 0)} 亿")
    else:
        st.info("北向资金数据暂不可用")

with col_f2:
    with st.spinner("加载融资融券..."):
        margin = get_margin_data()
    if margin:
        with st.container(border=True):
            st.markdown("**📊 融资融券**")
            emotion = margin.get("杠杆情绪", "")
            emoji = "🔥" if emotion == "加杠杆" else "❄️"
            st.metric(f"{emoji} {emotion}", f"融资余额 {margin.get('融资余额亿', 0)} 亿")
            st.caption(f"5日变化: {margin.get('融资5日变化亿', 0)} 亿 | 融券: {margin.get('融券余额亿', 0)} 亿")
    else:
        st.info("融资融券: 需配置 Tushare PRO")

with col_f3:
    with st.spinner("加载期货行情..."):
        futures = get_futures_overview()
    if futures:
        with st.container(border=True):
            st.markdown("**🛢️ 商品期货 (CTA参考)**")
            for name, data in list(futures.items())[:6]:
                chg = data.get("chg_pct", 0)
                arrow = "🟢" if chg > 0 else ("🔴" if chg < 0 else "⚪")
                st.caption(f"{arrow} {name}: {data.get('price', '—')} ({chg:+.1f}%)")
    else:
        st.info("期货数据暂不可用")

# ============================================================
# 第四层: 结构性主线 + 工具箱
# ============================================================
st.divider()
st.subheader("🧩 结构性主线与工具箱")

tab1, tab2, tab3, tab4 = st.tabs(["📦 ETF 工具箱", "🏭 行业板块", "🔥 概念热度", "📝 券商研报"])

with tab1:
    with st.spinner("加载 ETF 工具箱..."):
        etf_df = get_etf_list()
    if etf_df is not None and not etf_df.empty:
        show_cols = [c for c in ["代码", "名称", "最新价", "涨跌幅", "成交额"] if c in etf_df.columns]
        st.dataframe(etf_df[show_cols] if show_cols else etf_df, use_container_width=True, height=350)

with tab2:
    with st.spinner("扫描行业异动..."):
        ind_df = get_industry_board()
    if ind_df is not None and not ind_df.empty:
        show_cols = [c for c in ["板块名称", "涨跌幅", "总市值", "换手率", "上涨家数", "下跌家数"] if c in ind_df.columns]
        st.dataframe(ind_df[show_cols].head(30) if show_cols else ind_df.head(30), use_container_width=True, height=350)

with tab3:
    with st.spinner("扫描概念热度..."):
        con_df = get_concept_board()
    if con_df is not None and not con_df.empty:
        show_cols = [c for c in ["板块名称", "涨跌幅", "总市值", "换手率", "上涨家数", "下跌家数"] if c in con_df.columns]
        st.dataframe(con_df[show_cols].head(20) if show_cols else con_df.head(20), use_container_width=True, height=350)

with tab4:
    with st.spinner("加载券商研报..."):
        reports = get_research_reports(30)
    if reports:
        report_data = []
        for r in reports:
            rating_chg = ""
            if r.get("pre_rating") and r.get("rating") and r["pre_rating"] != r["rating"]:
                rating_chg = f"{r['pre_rating']}→{r['rating']}"
            else:
                rating_chg = r.get("rating", "")
            report_data.append({
                "股票": r.get("stock_name", ""),
                "券商": r.get("org_name", ""),
                "评级": rating_chg,
                "目标价": r.get("target_price", ""),
                "日期": r.get("report_date", ""),
            })
        st.dataframe(pd.DataFrame(report_data), use_container_width=True, height=350)
    else:
        st.info("券商研报: 需配置 Tushare PRO Token")

# 页脚
st.divider()
st.caption(f"更新时间: {datetime.now().strftime('%H:%M:%S')} · 数据源: AKShare" + (" + Tushare PRO" if _tushare_available() else "") + " · 仅供参考")
