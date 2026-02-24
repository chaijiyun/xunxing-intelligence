"""
📊 FOF 投研驾驶舱 V4 — 桥水式全维度市场仪表盘
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
    get_northbound_flow, get_margin_data, get_futures_overview,
    get_research_reports, get_liquidity_data, get_credit_spread,
    get_volatility_data, get_sentiment_temperature,
    _tushare_available,
)

st.set_page_config(page_title="FOF 驾驶舱", page_icon="📊", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("请先登录")
    st.page_link("app.py", label="🔐 返回登录", icon="🏠")
    st.stop()

st.title("📊 寻星 FOF 投研驾驶舱")
st.caption("桥水式全维度: 宏观四维 · 风格动量 · 波动率 · 资金 · 情绪 · 行业 · 工具")

col_r1, col_r2 = st.columns([1, 5])
with col_r1:
    if st.button("🔄 刷新", type="primary"):
        st.cache_data.clear()
        st.rerun()
with col_r2:
    ts_status = "✅ Tushare PRO (主)" if _tushare_available() else "⚠️ AKShare (降级)"
    st.info(f"数据源: {ts_status} | 框架: 增长→通胀→流动性→信用→风格→波动→资金→情绪")

st.divider()

# ============================================================
# 第一层: 桥水式宏观四维
# ============================================================
st.subheader("🧭 宏观环境 — 桥水四维框架")
col_m1, col_m2, col_m3, col_m4 = st.columns(4)

with col_m1:
    with st.spinner("宏观..."):
        macro = get_macro_data()
    with st.container(border=True):
        st.markdown("**📈 增长 & 通胀**")
        if macro:
            display = {k: v for k, v in macro.items()
                      if k not in ("CPI月份", "PMI月份") and v not in ("—", "超时", "", None)}
            if display:
                for k, v in display.items():
                    st.caption(f"{k}: **{v}**")
                cpi_m = macro.get("CPI月份", "")
                pmi_m = macro.get("PMI月份", "")
                if cpi_m or pmi_m:
                    st.caption(f"📅 CPI {cpi_m} | PMI {pmi_m}")
            else:
                st.caption("暂无数据")
        else:
            st.warning("宏观数据暂不可用")

with col_m2:
    with st.spinner("流动性..."):
        liquidity = get_liquidity_data()
    with st.container(border=True):
        st.markdown("**💧 流动性**")
        if liquidity:
            for k, v in liquidity.items():
                st.caption(f"{k}: **{v}**")
        else:
            st.caption("暂无数据")

with col_m3:
    with st.spinner("信用..."):
        credit = get_credit_spread()
    with st.container(border=True):
        st.markdown("**🏦 信用环境**")
        if credit:
            for k, v in credit.items():
                st.caption(f"{k}: **{v}**")
        else:
            st.caption("暂无数据")

with col_m4:
    with st.spinner("波动率..."):
        volatility = get_volatility_data()
    with st.container(border=True):
        st.markdown("**📊 波动率 & 量能**")
        if volatility:
            for k, v in volatility.items():
                st.caption(f"{k}: **{v}**")
        else:
            st.caption("暂无数据")

# ============================================================
# 第二层: 风格动量 (5日 + 20日)
# ============================================================
st.divider()
st.subheader("🎭 市场风格与动量")

with st.spinner("风格..."):
    style = get_style_data()

if style:
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        with st.container(border=True):
            st.markdown("**📐 大小盘风格**")
            sc1, sc2 = st.columns(2)
            with sc1:
                st.metric("5日偏好", style.get("大小盘偏好_5日", "—"))
                st.caption(f"沪深300: {style.get('沪深300_5日', '—')}%")
                st.caption(f"中证1000: {style.get('中证1000_5日', '—')}%")
            with sc2:
                st.metric("20日趋势", style.get("大小盘偏好_20日", "—"))
                st.caption(f"沪深300: {style.get('沪深300_20日', '—')}%")
                st.caption(f"中证1000: {style.get('中证1000_20日', '—')}%")
    with col_s2:
        with st.container(border=True):
            st.markdown("**🎯 成长/价值风格**")
            sc3, sc4 = st.columns(2)
            with sc3:
                st.metric("5日偏好", style.get("成长价值_5日", "—"))
                st.caption(f"创业板指: {style.get('创业板指_5日', '—')}%")
                st.caption(f"上证50: {style.get('上证50_5日', '—')}%")
            with sc4:
                st.metric("20日趋势", style.get("成长价值_20日", "—"))
                st.caption(f"创业板指: {style.get('创业板指_20日', '—')}%")
                st.caption(f"上证50: {style.get('上证50_20日', '—')}%")
    if "中证500_5日" in style:
        st.caption(f"中证500: 5日 {style.get('中证500_5日', '')}% | 20日 {style.get('中证500_20日', '')}%")
else:
    st.warning("风格数据暂不可用")

# ============================================================
# 第三层: 指数 + 涨跌 + 情绪温度计
# ============================================================
st.divider()
st.subheader("📈 宽基指数与市场情绪")

with st.spinner("指数..."):
    idx_df = get_major_indices()

if idx_df is not None and not idx_df.empty and "error" not in idx_df.columns:
    cols = st.columns(min(len(idx_df), 7))
    for i, (_, row) in enumerate(idx_df.iterrows()):
        if i >= len(cols):
            break
        with cols[i]:
            price = row.get("最新价", 0)
            chg = row.get("涨跌幅", 0)
            st.metric(
                row.get("名称", ""),
                f"{price:,.2f}" if pd.notna(price) else "—",
                f"{chg:+.2f}%" if pd.notna(chg) else "—",
                delta_color="normal" if (pd.notna(chg) and chg >= 0) else "inverse",
            )

with st.spinner("涨跌统计..."):
    ov = get_market_overview()

# 预加载资金数据 (后面也要用)
nb_data = get_northbound_flow()
margin_data = get_margin_data()

if ov and "error" not in ov:
    col_ov1, col_ov2 = st.columns([3, 1])
    with col_ov1:
        with st.container(border=True):
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("上涨", ov.get("上涨", 0), f"{ov.get('上涨占比', 0)}%")
            c2.metric("下跌", ov.get("下跌", 0))
            c3.metric("涨停", ov.get("涨停", 0))
            c4.metric("跌停", ov.get("跌停", 0))
            c5.metric("强势(>3%)", ov.get("强势股", 0))
            c6.metric("成交额", f"{ov.get('总成交额亿', 0):,.0f}亿")
    with col_ov2:
        sentiment = get_sentiment_temperature(ov, nb_data, margin_data, volatility)
        with st.container(border=True):
            st.markdown("**🌡️ 情绪温度**")
            temp = sentiment.get("温度", 50)
            st.metric("综合", f"{temp:.0f}", sentiment.get("级别", ""))
            for k, v in sentiment.get("分项", {}).items():
                st.caption(f"{k}: {v:.0f}")

# ============================================================
# 第四层: 资金 + 期货
# ============================================================
st.divider()
st.subheader("💰 资金流向与商品期货")

col_f1, col_f2, col_f3 = st.columns(3)

with col_f1:
    if nb_data:
        with st.container(border=True):
            st.markdown("**🌏 北向资金**")
            direction = nb_data.get("方向", "")
            color = "🟢" if "入" in direction else "🔴"
            st.metric(f"{color} {direction}", f"{nb_data.get('今日净流入亿', 0)} 亿")
            st.caption(f"5日均值: {nb_data.get('5日均值亿', 0)} 亿")
    else:
        st.info("北向资金暂不可用")

with col_f2:
    if margin_data:
        with st.container(border=True):
            st.markdown("**📊 融资融券**")
            emotion = margin_data.get("杠杆情绪", "")
            emoji = "🔥" if emotion == "加杠杆" else "❄️"
            st.metric(f"{emoji} {emotion}", f"融资 {margin_data.get('融资余额亿', 0)} 亿")
            st.caption(f"5日变化: {margin_data.get('融资5日变化亿', 0)} 亿 | 融券: {margin_data.get('融券余额亿', 0)} 亿")
    else:
        st.info("融资融券: 需配置 Tushare PRO")

with col_f3:
    with st.spinner("期货..."):
        futures = get_futures_overview()
    if futures:
        with st.container(border=True):
            st.markdown("**🛢️ 商品期货 (CTA)**")
            for name, data in list(futures.items())[:6]:
                chg = data.get("chg_pct", 0)
                arrow = "🟢" if chg > 0 else ("🔴" if chg < 0 else "⚪")
                st.caption(f"{arrow} {name}: {data.get('price', '—')} ({chg:+.1f}%)")
    else:
        st.info("期货暂不可用")

# ============================================================
# 第五层: 板块 + ETF + 研报
# ============================================================
st.divider()
st.subheader("🧩 结构性主线与工具箱")

tab1, tab2, tab3, tab4 = st.tabs(["📦 ETF", "🏭 行业板块", "🔥 概念热度", "📝 券商研报"])

with tab1:
    with st.spinner("ETF..."):
        etf_df = get_etf_list()
    if etf_df is not None and not etf_df.empty:
        show = [c for c in ["代码", "名称", "最新价", "涨跌幅", "成交额"] if c in etf_df.columns]
        st.dataframe(etf_df[show] if show else etf_df, use_container_width=True, height=350)
    else:
        st.info("ETF 数据暂不可用")

with tab2:
    with st.spinner("行业..."):
        ind_df = get_industry_board()
    if ind_df is not None and not ind_df.empty:
        show = [c for c in ["板块名称", "涨跌幅", "总市值", "换手率", "上涨家数", "下跌家数"] if c in ind_df.columns]
        st.dataframe(ind_df[show].head(30) if show else ind_df.head(30), use_container_width=True, height=350)
    else:
        st.info("行业板块暂不可用")

with tab3:
    with st.spinner("概念..."):
        con_df = get_concept_board()
    if con_df is not None and not con_df.empty:
        show = [c for c in ["板块名称", "涨跌幅", "总市值", "换手率", "上涨家数", "下跌家数"] if c in con_df.columns]
        st.dataframe(con_df[show].head(20) if show else con_df.head(20), use_container_width=True, height=350)
    else:
        st.info("概念板块暂不可用")

with tab4:
    with st.spinner("研报..."):
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
        st.info("券商研报: 需配置 Tushare PRO")

# 页脚
st.divider()
data_src = "Tushare PRO (主) + AKShare (辅)" if _tushare_available() else "AKShare"
st.caption(f"更新: {datetime.now().strftime('%H:%M:%S')} · 数据源: {data_src} · 仅供参考")
