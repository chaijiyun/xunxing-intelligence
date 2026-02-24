"""
📝 CIO 日报 - FOF 配置决策中心
================================================================
升级 V3: 使用数据打包 + FOF 专业 Prompt + 结构化配置输出
================================================================
"""
import streamlit as st
import json
import os
from datetime import datetime
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_fetcher import (
    get_daily_data_pack, pack_market_text, pack_news_text, _tushare_available,
)
from utils.ai_analyzer import generate_daily_report

st.set_page_config(page_title="CIO 日报", page_icon="📝", layout="wide")
st.title("📝 寻星 CIO 日报")
st.caption("AI 综合分析 · 大类配置 · FOF 策略权重 · 行业方向 · 个股线索")
st.divider()

# ============================================================
# 状态检查
# ============================================================
api_key = ""
try:
    api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
except Exception:
    pass
has_api = bool(api_key and not api_key.startswith("sk-xxxx"))
has_tushare = _tushare_available()

col_s1, col_s2 = st.columns(2)
with col_s1:
    if has_api:
        st.success("🤖 DeepSeek AI: 已连接")
    else:
        st.error("🤖 DeepSeek AI: 未配置")
with col_s2:
    if has_tushare:
        st.success("📡 Tushare PRO: 已连接")
    else:
        st.warning("📡 Tushare PRO: 未配置 (资讯将使用新浪降级源)")

if not has_api:
    st.warning("""
⚠️ **未配置 DeepSeek API Key** — 研报需要 AI 能力

1. 注册 [platform.deepseek.com](https://platform.deepseek.com/)
2. 创建 API Key，充值10元
3. Streamlit Cloud → Settings → Secrets 添加：
```
DEEPSEEK_API_KEY = "sk-你的密钥"
```
    """)

st.divider()

# ============================================================
# 缓存
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
today_file = os.path.join(DATA_DIR, f"report_{datetime.now().strftime('%Y%m%d')}.json")


def load_cache():
    if os.path.exists(today_file):
        with open(today_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(data):
    with open(today_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


cached = load_cache()
if cached:
    st.info(f"📄 已有今日缓存报告（{cached.get('time', '')}）· 数据源: {cached.get('data_sources', 'unknown')}")

# ============================================================
# 操作按钮
# ============================================================
c1, c2 = st.columns(2)
with c1:
    gen_btn = st.button("🚀 生成新报告", type="primary", use_container_width=True, disabled=not has_api)
with c2:
    load_btn = st.button("📄 查看缓存报告", use_container_width=True, disabled=not cached)

report = None

# ============================================================
# 生成报告
# ============================================================
if gen_btn and has_api:
    progress = st.progress(0, "准备中...")

    # Stage 1: 全量数据采集
    progress.progress(10, "📡 采集行情 + 宏观 + 资金流向 + 期货...")
    data_pack = get_daily_data_pack()

    # 显示采集状态
    sources_status = []
    if data_pack.get("indices") is not None and not data_pack["indices"].empty:
        sources_status.append("✅指数")
    if data_pack.get("overview"):
        sources_status.append("✅涨跌")
    if data_pack.get("macro"):
        sources_status.append("✅宏观")
    if data_pack.get("northbound"):
        sources_status.append("✅北向")
    if data_pack.get("margin"):
        sources_status.append("✅融资")
    if data_pack.get("futures"):
        sources_status.append("✅期货")
    if data_pack.get("news"):
        sources_status.append(f"✅资讯({len(data_pack['news'])}条)")
    if data_pack.get("research"):
        sources_status.append(f"✅研报({len(data_pack['research'])}条)")

    progress.progress(40, f"📊 数据采集完成: {' '.join(sources_status)}")

    # Stage 2: 数据打包为文本
    progress.progress(50, "📦 数据打包...")
    market_text = pack_market_text(data_pack)
    news_text = pack_news_text(data_pack)

    # Stage 3: AI 生成报告
    progress.progress(60, "🤖 DeepSeek 正在生成 CIO 配置报告...")
    report = generate_daily_report(market_text, news_text)

    # Stage 4: 保存
    progress.progress(90, "💾 保存...")
    data_sources = "Tushare+AKShare+新浪" if has_tushare else "AKShare+新浪"
    save_cache({
        "time": datetime.now().strftime("%H:%M"),
        "report": report,
        "data_sources": data_sources,
        "market_text_preview": market_text[:500],
        "news_count": len(data_pack.get("news", [])),
        "research_count": len(data_pack.get("research", [])),
    })

    progress.progress(100, "✅ 完成!")
    st.balloons()

elif load_btn and cached:
    report = cached.get("report", "")

# ============================================================
# 展示报告
# ============================================================
if report:
    st.divider()

    # 报告头
    st.markdown(f"""
<div style="padding:16px 20px; border-radius:10px;
background: linear-gradient(135deg, rgba(255,107,53,0.12), rgba(69,183,209,0.06));
border: 1px solid rgba(255,107,53,0.25); margin-bottom:20px;">
<h2 style="margin:0; color:#FF6B35;">🔭 寻星 FOF CIO 日报</h2>
<p style="margin:4px 0 0; color:#999;">{datetime.now().strftime('%Y年%m月%d日')} · DeepSeek V3 · 数据源: {'Tushare PRO + AKShare' if has_tushare else 'AKShare + 新浪'}</p>
</div>""", unsafe_allow_html=True)

    # 报告正文
    st.markdown(report)

    st.divider()

    # 下载
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "📄 下载 Markdown",
            report,
            f"寻星CIO日报_{datetime.now().strftime('%Y%m%d')}.md",
            "text/markdown",
            use_container_width=True,
        )
    with c2:
        st.download_button(
            "📝 下载 TXT",
            report.replace("###", "").replace("**", ""),
            f"寻星CIO日报_{datetime.now().strftime('%Y%m%d')}.txt",
            "text/plain",
            use_container_width=True,
        )

    # 数据诊断折叠面板
    with st.expander("🔍 本次报告数据诊断"):
        if cached:
            st.markdown(f"- 资讯条数: {cached.get('news_count', '?')}")
            st.markdown(f"- 研报条数: {cached.get('research_count', '?')}")
            st.markdown(f"- 数据源: {cached.get('data_sources', '?')}")
            if cached.get("market_text_preview"):
                st.text(cached["market_text_preview"])

else:
    if not gen_btn:
        st.markdown("""
### 📋 报告包含以下决策模块

| 模块 | 内容 | 对应你的需求 |
|------|------|-------------|
| **一、宏观周期判断** | 复苏/过热/滞胀/衰退定性 | 大类资产方向的理论基础 |
| **二、大类资产配置** | 权益/固收/商品/现金具体比例 | 股票、债券、商品的配置权重 |
| **三、FOF策略配置** | 7项策略具体比例(合计100%) | 多头/指增/中性/CTA/套利/固收+ |
| **四、风格与行业** | 大小盘+成长价值+TOP3行业 | 市场风格方向+行业方向 |
| **五、战术工具箱** | ETF代码+个股线索 | 具体的执行工具 |
| **六、风险预警** | 3大风险+对冲建议 | 防御配置和尾部风险管理 |

👆 点击 **「生成新报告」** 开始

---

**💡 数据源说明**:
- **Tushare PRO** (已配置✅): 财经新闻、新闻联播、券商研报评级、融资融券
- **AKShare** (免费): A股行情、指数、板块、ETF、宏观数据、北向资金、期货
- **新浪快讯** (补充): 盘中异动实时快讯
        """)

st.divider()
st.caption(f"寻星配置跟踪系统 · v3.0 · {datetime.now().strftime('%H:%M:%S')}")
