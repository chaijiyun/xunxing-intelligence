"""
📈 量化选股模型 V1 — 多因子强势股筛选
================================================================
三维共振: 量价趋势 + 资金流向 + 新闻催化
因子体系: 动量/均线/MACD/RSI/量价/资金/突破
================================================================
"""
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_fetcher import (
    _tushare_available, get_market_snapshot, get_multi_stock_daily,
    get_market_moneyflow, get_industry_moneyflow,
    calc_technical_factors, calc_moneyflow_factors,
    quant_stock_screener, get_stock_daily, get_stock_moneyflow,
)
from utils.ai_analyzer import _get_api_key, _call_deepseek

st.set_page_config(page_title="量化选股", page_icon="📈", layout="wide")

# 登录检查
if not st.session_state.get("authenticated"):
    st.warning("请先登录")
    st.page_link("app.py", label="🔐 返回登录", icon="🏠")
    st.stop()

st.title("📈 寻星量化选股模型")
st.caption("三维共振: 量价趋势 × 资金流向 × 技术形态 | 多因子加权打分 → 强势股 TOP 30")

if not _tushare_available():
    st.error("⚠️ 量化选股模块需要 Tushare PRO，请先配置 TUSHARE_TOKEN")
    st.stop()

st.divider()

# ============================================================
# 控制面板
# ============================================================
st.subheader("⚙️ 选股参数")

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
with col_p1:
    min_amount = st.number_input("最低成交额 (万元)", value=5000, step=1000,
                                  help="过滤流动性不足的个股")
with col_p2:
    top_n = st.slider("输出TOP N", 10, 50, 30, step=5)
with col_p3:
    pool_size = st.slider("候选池大小", 50, 300, 200, step=50,
                          help="从成交额排名前N只中筛选")
with col_p4:
    st.write("")
    run_btn = st.button("🚀 启动选股", type="primary", use_container_width=True)

# 因子权重调节
with st.expander("🎛️ 因子权重调节 (高级)", expanded=False):
    st.caption("调整各因子在综合打分中的权重，合计应为100%")

    wc1, wc2, wc3, wc4 = st.columns(4)
    with wc1:
        st.markdown("**📊 趋势动量**")
        w_momentum = st.slider("动量_20日", 0, 40, 15, key="w1")
        w_ma = st.slider("均线多头", 0, 30, 10, key="w2")
    with wc2:
        st.markdown("**📈 技术信号**")
        w_macd = st.slider("MACD金叉", 0, 30, 10, key="w3")
        w_rsi = st.slider("RSI动能", 0, 30, 10, key="w4")
    with wc3:
        st.markdown("**🔊 量价关系**")
        w_vol = st.slider("量比_5/20", 0, 40, 15, key="w5")
        w_breakout = st.slider("20日新高", 0, 30, 10, key="w6")
    with wc4:
        st.markdown("**💰 资金流向**")
        w_money = st.slider("主力净流入_5日", 0, 40, 20, key="w7")
        w_consec = st.slider("连续流入天数", 0, 30, 10, key="w8")

    total_w = w_momentum + w_ma + w_macd + w_rsi + w_vol + w_breakout + w_money + w_consec
    if total_w != 100:
        st.warning(f"当前权重合计: {total_w}%，建议调整为100%")
    else:
        st.success(f"权重合计: {total_w}% ✅")

    custom_weights = {
        "动量_20日": w_momentum / 100,
        "均线多头": w_ma / 100,
        "MACD金叉": w_macd / 100,
        "RSI_14": w_rsi / 100,
        "量比_5/20": w_vol / 100,
        "20日新高": w_breakout / 100,
        "主力净流入_5日": w_money / 100,
        "主力连续流入天数": w_consec / 100,
    }

# Session state
if "quant_result" not in st.session_state:
    st.session_state.quant_result = None
if "quant_industry_flow" not in st.session_state:
    st.session_state.quant_industry_flow = None

# ============================================================
# 执行选股
# ============================================================
if run_btn:
    st.divider()

    # Phase 1: 行业资金扫描
    with st.spinner("📡 Phase 1/3: 扫描行业资金流向..."):
        ind_flow = get_industry_moneyflow()
        st.session_state.quant_industry_flow = ind_flow

    if ind_flow is not None and not ind_flow.empty:
        st.subheader("🏭 行业资金流向 (今日)")
        with st.container(border=True):
            # 净流入TOP5 行业
            if "industry_name" in ind_flow.columns and "net_amount" in ind_flow.columns:
                top5 = ind_flow.head(5)
                bot5 = ind_flow.tail(5)
                tc1, tc2 = st.columns(2)
                with tc1:
                    st.markdown("**🟢 净流入 TOP5**")
                    for _, r in top5.iterrows():
                        name = r.get("industry_name", "")
                        net = float(r.get("net_amount", 0))
                        st.caption(f"🟢 {name}: {net/1e4:+,.0f}万")
                with tc2:
                    st.markdown("**🔴 净流出 TOP5**")
                    for _, r in bot5.iterrows():
                        name = r.get("industry_name", "")
                        net = float(r.get("net_amount", 0))
                        st.caption(f"🔴 {name}: {net/1e4:+,.0f}万")
            else:
                show_cols = [c for c in ind_flow.columns[:6]]
                st.dataframe(ind_flow[show_cols].head(10), use_container_width=True)
    else:
        st.info("行业资金流向数据暂不可用")

    # Phase 2: 多因子选股
    progress = st.progress(0, "Phase 2/3: 多因子选股引擎启动...")

    with st.spinner("📊 Phase 2/3: 全市场扫描 + 因子计算 + 综合打分... (约30-60秒)"):
        progress.progress(20, "获取全市场行情快照...")
        result = quant_stock_screener(
            min_amount=min_amount,
            top_n=top_n,
            factors_weight=custom_weights,
        )
        progress.progress(80, "综合打分排名中...")
        st.session_state.quant_result = result
        progress.progress(100, "✅ 选股完成!")

# ============================================================
# 展示结果
# ============================================================
result = st.session_state.quant_result

if result is not None and not result.empty:
    st.divider()
    st.subheader(f"🏆 强势股 TOP {len(result)}")

    # 概览指标
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("入选股票数", f"{len(result)} 只")
    avg_score = result["综合得分"].mean()
    mc2.metric("平均得分", f"{avg_score:.1f}")
    if "涨跌幅" in result.columns:
        avg_chg = result["涨跌幅"].mean()
        mc3.metric("平均涨幅", f"{avg_chg:+.2f}%")
    if "行业" in result.columns:
        top_ind = result["行业"].value_counts()
        if not top_ind.empty:
            mc4.metric("主要行业", f"{top_ind.index[0]} ({top_ind.iloc[0]}只)")

    # 核心展示列
    display_cols = ["ts_code", "名称", "行业", "综合得分", "涨跌幅", "成交额万"]

    # 因子详情列
    factor_cols = ["动量_5日", "动量_20日", "均线多头", "MACD金叉", "RSI_14",
                   "量比_5/20", "20日新高", "主力净流入_5日", "主力连续流入天数"]

    available_display = [c for c in display_cols if c in result.columns]
    available_factors = [c for c in factor_cols if c in result.columns]

    # 主表格
    st.markdown("**📋 综合排名**")
    show_df = result[available_display + available_factors].copy() if available_factors else result[available_display].copy()
    st.dataframe(
        show_df,
        use_container_width=True,
        height=min(len(result) * 38 + 40, 800),
        column_config={
            "综合得分": st.column_config.ProgressColumn(
                "综合得分", format="%.1f", min_value=0, max_value=100),
            "涨跌幅": st.column_config.NumberColumn("涨跌幅%", format="%.2f"),
        }
    )

    # 行业分布
    if "行业" in result.columns:
        st.divider()
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("**🏭 行业分布**")
            ind_dist = result["行业"].value_counts().head(10)
            if not ind_dist.empty:
                st.bar_chart(ind_dist, height=250)
        with col_c2:
            st.markdown("**📊 得分分布**")
            if len(result) >= 3:
                score_bins = pd.cut(result["综合得分"], bins=5)
                st.bar_chart(score_bins.value_counts().sort_index(), height=250)

    # ============================================================
    # Phase 3: AI 深度点评 (可选)
    # ============================================================
    st.divider()
    st.subheader("🤖 AI 选股点评")

    if _get_api_key():
        ai_btn = st.button("⚡ DeepSeek 深度分析 TOP 10", type="primary")
        if ai_btn:
            top10 = result.head(10)
            stock_summary = ""
            for _, row in top10.iterrows():
                ts_code = row.get("ts_code", "")
                name = row.get("名称", "")
                industry = row.get("行业", "")
                score = row.get("综合得分", 0)
                chg = row.get("涨跌幅", 0)
                momentum = row.get("动量_20日", "")
                vol_ratio = row.get("量比_5/20", "")
                macd = "金叉" if row.get("MACD金叉", 0) == 1 else "非金叉"
                ma = "多头" if row.get("均线多头", 0) == 1 else "非多头"
                rsi = row.get("RSI_14", "")
                money5 = row.get("主力净流入_5日", "")
                consec = row.get("主力连续流入天数", "")
                new_high = "是" if row.get("20日新高", 0) == 1 else "否"

                stock_summary += f"\n{name}({ts_code}) | 行业:{industry} | 得分:{score:.1f}"
                stock_summary += f"\n  今日涨幅:{chg:+.2f}% | 20日动量:{momentum}% | 量比:{vol_ratio}"
                stock_summary += f"\n  MACD:{macd} | 均线:{ma} | RSI:{rsi} | 20日新高:{new_high}"
                stock_summary += f"\n  主力5日净流入:{money5} | 连续流入:{consec}天\n"

            with st.spinner("🤖 DeepSeek 正在分析 TOP 10 强势股..."):
                prompt = f"""作为寻星FOF的CIO，基于以下量化选股模型输出的TOP 10强势股，给出专业点评。

【选股模型】多因子打分: 趋势动量(15%) + 均线(10%) + MACD(10%) + RSI(10%) + 量价(15%) + 资金流向(30%) + 突破(10%)

【TOP 10 强势股】
{stock_summary}

请按以下格式分析:
### 🏆 TOP 10 强势股点评

**整体特征**: (共性分析: 集中在什么行业？什么风格？量价资金有何共同特点？)

**个股精评** (每只1-2句话):
1. XX: 强在哪里？风险在哪？
...

**配置建议**:
- 短线(1-3天): XX只最适合短线，理由
- 波段(1-2周): XX只有波段机会，理由
- 风险提示: 哪些需要注意的

**与FOF策略的关联**:
- 这些选股结果对FOF的指增/多头策略意味着什么？"""

                ai_result = _call_deepseek(prompt,
                    "你是寻星FOF的CIO，擅长量化分析和技术分析，给出专业但简洁的投资点评。",
                    temperature=0.3, max_tokens=3000)

                st.markdown("""
                <div style="padding:16px 20px; border-radius:10px;
                background: linear-gradient(135deg, rgba(255,107,53,0.1), rgba(69,183,209,0.05));
                border: 1px solid rgba(255,107,53,0.2);">
                """, unsafe_allow_html=True)
                st.markdown(ai_result)
                st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("💡 配置 DeepSeek API Key 后可启用 AI 深度点评")

    # ============================================================
    # 个股详情 (可选)
    # ============================================================
    st.divider()
    st.subheader("🔍 个股因子详情")

    stock_options = [f"{row.get('名称', '')} ({row.get('ts_code', '')})" for _, row in result.head(20).iterrows()]
    if stock_options:
        selected = st.selectbox("选择个股查看详情", stock_options)
        if selected:
            ts_code = selected.split("(")[1].rstrip(")")
            stock_row = result[result["ts_code"] == ts_code]

            if not stock_row.empty:
                row = stock_row.iloc[0]

                dc1, dc2, dc3 = st.columns(3)
                with dc1:
                    with st.container(border=True):
                        st.markdown("**📊 趋势因子**")
                        st.caption(f"5日动量: {row.get('动量_5日', '—')}%")
                        st.caption(f"10日动量: {row.get('动量_10日', '—')}%")
                        st.caption(f"20日动量: {row.get('动量_20日', '—')}%")
                        st.caption(f"60日动量: {row.get('动量_60日', '—')}%")
                        st.caption(f"均线多头: {'✅' if row.get('均线多头', 0) == 1 else '❌'}")
                        st.caption(f"MA5/MA20/MA60: {row.get('MA5', '—')}/{row.get('MA20', '—')}/{row.get('MA60', '—')}")

                with dc2:
                    with st.container(border=True):
                        st.markdown("**📈 技术因子**")
                        st.caption(f"MACD: DIF={row.get('MACD_DIF', '—')} DEA={row.get('MACD_DEA', '—')}")
                        st.caption(f"MACD柱: {row.get('MACD柱', '—')}")
                        st.caption(f"MACD金叉: {'✅' if row.get('MACD金叉', 0) == 1 else '❌'}")
                        st.caption(f"RSI_14: {row.get('RSI_14', '—')}")
                        st.caption(f"布林位置: {row.get('布林位置', '—')}")
                        st.caption(f"ATR/价格: {row.get('ATR/价格%', '—')}%")

                with dc3:
                    with st.container(border=True):
                        st.markdown("**💰 资金因子**")
                        st.caption(f"量比(5/20): {row.get('量比_5/20', '—')}")
                        st.caption(f"今日量比: {row.get('今日量比', '—')}")
                        st.caption(f"主力净流入_5日: {row.get('主力净流入_5日', '—')}")
                        st.caption(f"连续流入天数: {row.get('主力连续流入天数', '—')}")
                        st.caption(f"20日新高: {'✅' if row.get('20日新高', 0) == 1 else '❌'}")
                        st.caption(f"连涨天数: {row.get('连涨天数', '—')}")

elif result is not None and result.empty:
    st.warning("未筛选到符合条件的股票，请调整参数后重试")

else:
    # 首次进入 — 模型说明
    st.divider()
    st.markdown("""
### 📐 模型架构

本模型采用**三维共振**理念: 只有当**量价趋势 + 资金流向 + 技术形态**同时确认时，才认定为强势股。

| 维度 | 因子 | 权重 | 逻辑 |
|------|------|------|------|
| **趋势动量** | 20日涨幅 | 15% | 中期趋势强度 |
| **量价关系** | 量比(5日/20日均量) | 15% | 放量确认趋势 |
| **资金流向** | 主力5日净流入 | 20% | 聪明钱方向 (最大权重) |
| **技术形态** | MACD金叉 | 10% | 短期反转/启动信号 |
| **趋势确认** | 均线多头排列 | 10% | MA5>MA20 确认 |
| **动能** | RSI(14) | 10% | 50-80区间最佳 |
| **突破** | 20日新高 | 10% | 价格突破信号 |
| **持续性** | 主力连续流入天数 | 10% | 资金持续性 |

**数据源**: Tushare PRO (A股日线行情 + 个股资金流向 + 行业资金流向)

**筛选流程**:
1. 全A股行情快照 → 过滤ST/新股/流动性不足/涨跌停
2. 成交额TOP200 → 批量获取60日日线 + 资金流向
3. 逐只计算8大因子 → 加权打分
4. 综合排名 TOP N → 可选 AI 深度点评

👆 点击 **「启动选股」** 开始
    """)

# 页脚
st.divider()
st.caption(f"寻星量化选股 · V1 · {datetime.now().strftime('%H:%M:%S')} · 数据源: Tushare PRO · 仅供参考")
