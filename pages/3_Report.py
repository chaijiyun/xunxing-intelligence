"""
📝 CIO 日报 V4 - FOF 配置决策中心
================================================================
V4: 全量数据驱动 + 数据质量审计 + 桥水四维框架
================================================================
"""
import streamlit as st
import json
import os
from datetime import datetime
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_fetcher import (
    get_daily_data_pack, pack_market_text, pack_news_text,
    _tushare_available, get_sentiment_temperature,
)
from utils.ai_analyzer import generate_daily_report

st.set_page_config(page_title="CIO 日报", page_icon="📝", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("请先登录")
    st.page_link("app.py", label="🔐 返回登录", icon="🏠")
    st.stop()

st.title("📝 寻星 CIO 日报")
st.caption("AI 全量数据驱动 · 桥水四维宏观 · 大类配置 · FOF策略 · 风控预案")
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
        st.success("📡 Tushare PRO: 已连接 (主力数据源)")
    else:
        st.warning("📡 Tushare PRO: 未配置 (降级至 AKShare)")

if not has_api:
    st.warning("""
⚠️ **未配置 DeepSeek API Key** — CIO 日报需要 AI

1. 注册 [platform.deepseek.com](https://platform.deepseek.com/)
2. 创建 API Key
3. Streamlit Cloud → Settings → Secrets:
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
    st.info(f"📄 已有今日缓存（{cached.get('time', '')}）· 数据维度: {cached.get('data_dimensions', '?')} · 数据源: {cached.get('data_sources', '?')}")

# ============================================================
# 按钮
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
    progress.progress(10, "📡 采集全量数据: 行情+宏观+流动性+信用+波动率+资金+期货+资讯+研报...")
    data_pack = get_daily_data_pack()

    # 数据质量审计
    data_audit = []
    dim_count = 0
    if data_pack.get("indices") is not None and not data_pack["indices"].empty:
        data_audit.append("✅指数")
        dim_count += 1
    else:
        data_audit.append("❌指数")
    if data_pack.get("overview"):
        data_audit.append("✅涨跌")
        dim_count += 1
    else:
        data_audit.append("❌涨跌")
    if data_pack.get("macro"):
        data_audit.append(f"✅宏观({len(data_pack['macro'])}项)")
        dim_count += 1
    else:
        data_audit.append("❌宏观")
    if data_pack.get("liquidity"):
        data_audit.append(f"✅流动性({len(data_pack['liquidity'])}项)")
        dim_count += 1
    else:
        data_audit.append("⚠️流动性(缺)")
    if data_pack.get("credit"):
        data_audit.append("✅信用")
        dim_count += 1
    else:
        data_audit.append("⚠️信用(缺)")
    if data_pack.get("style"):
        data_audit.append(f"✅风格({len(data_pack['style'])}项)")
        dim_count += 1
    else:
        data_audit.append("❌风格")
    if data_pack.get("volatility"):
        data_audit.append("✅波动率")
        dim_count += 1
    else:
        data_audit.append("⚠️波动率(缺)")
    if data_pack.get("northbound"):
        data_audit.append("✅北向")
        dim_count += 1
    else:
        data_audit.append("⚠️北向(缺)")
    if data_pack.get("margin"):
        data_audit.append("✅融资")
        dim_count += 1
    else:
        data_audit.append("⚠️融资(缺)")
    if data_pack.get("futures"):
        data_audit.append(f"✅期货({len(data_pack['futures'])}品种)")
        dim_count += 1
    else:
        data_audit.append("⚠️期货(缺)")
    if data_pack.get("news"):
        data_audit.append(f"✅资讯({len(data_pack['news'])}条)")
        dim_count += 1
    else:
        data_audit.append("❌资讯")
    if data_pack.get("research"):
        data_audit.append(f"✅研报({len(data_pack['research'])}条)")
        dim_count += 1
    else:
        data_audit.append("⚠️研报(缺)")

    progress.progress(40, f"📊 数据审计完成: {dim_count}/12 维度 | {' '.join(data_audit)}")

    # Stage 2: 数据打包
    progress.progress(50, "📦 数据打包 (桥水四维 + 全量市场)...")
    market_text = pack_market_text(data_pack)
    news_text = pack_news_text(data_pack)

    # 显示数据输入规模
    total_chars = len(market_text) + len(news_text)
    st.caption(f"📏 AI 输入规模: 市场数据 {len(market_text)} 字 + 资讯 {len(news_text)} 字 = {total_chars} 字")

    # Stage 3: AI 生成
    progress.progress(60, "🤖 DeepSeek 正在生成 CIO 配置报告 (桥水四维框架)...")
    report = generate_daily_report(market_text, news_text)

    # Stage 4: 保存
    progress.progress(90, "💾 保存...")
    data_sources = "Tushare PRO (主) + AKShare (辅)" if has_tushare else "AKShare"
    save_cache({
        "time": datetime.now().strftime("%H:%M"),
        "report": report,
        "data_sources": data_sources,
        "data_dimensions": dim_count,
        "data_audit": data_audit,
        "market_text_preview": market_text[:800],
        "news_count": len(data_pack.get("news", [])),
        "research_count": len(data_pack.get("research", [])),
        "input_chars": total_chars,
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

    st.markdown(f"""
<div style="padding:16px 20px; border-radius:10px;
background: linear-gradient(135deg, rgba(255,107,53,0.12), rgba(69,183,209,0.06));
border: 1px solid rgba(255,107,53,0.25); margin-bottom:20px;">
<h2 style="margin:0; color:#FF6B35;">🔭 寻星 FOF CIO 日报</h2>
<p style="margin:4px 0 0; color:#999;">{datetime.now().strftime('%Y年%m月%d日')} · DeepSeek V3 · 桥水四维框架 · 数据源: {'Tushare PRO + AKShare' if has_tushare else 'AKShare'}</p>
</div>""", unsafe_allow_html=True)

    st.markdown(report)
    st.divider()

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

    with st.expander("🔍 数据质量审计"):
        if cached:
            st.markdown(f"- 数据维度: **{cached.get('data_dimensions', '?')}/12**")
            audit = cached.get("data_audit", [])
            if audit:
                st.markdown(f"- 详情: {' | '.join(audit)}")
            st.markdown(f"- 资讯: {cached.get('news_count', '?')} 条")
            st.markdown(f"- 研报: {cached.get('research_count', '?')} 条")
            st.markdown(f"- AI输入: {cached.get('input_chars', '?')} 字")
            st.markdown(f"- 数据源: {cached.get('data_sources', '?')}")
            if cached.get("market_text_preview"):
                st.text(cached["market_text_preview"])

else:
    if not gen_btn:
        st.markdown("""
### 📋 V4 报告包含以下决策模块

| 模块 | 内容 | 数据依据 |
|------|------|---------|
| **一、宏观周期** | 桥水四维: 增长/通胀/流动性/信用 | PMI/CPI/PPI/M2/Shibor/社融/信用利差 |
| **二、大类配置** | 权益/固收/商品/现金 = 100% | 宏观周期定位 + 美林时钟 |
| **三、FOF策略** | 7策略权重 = 100% | 波动率/风格/量能 → 策略适配 |
| **四、风格行业** | 大小盘+成长价值+TOP3行业 | 5日+20日动量 + 资金流向 |
| **五、工具箱** | ETF代码 + 个股线索 | 行业催化剂 + 研报评级 |
| **六、风险预警** | 3大风险 + 对冲预案 | 波动率 + 情绪温度 + 资金 |
| **七、数据自检** | 数据完整性审计 | 12维数据覆盖率 |

👆 点击 **「生成新报告」** 开始

**数据架构**: Tushare PRO (主) → AKShare (降级兜底) · 12+ 数据维度全量输入
        """)

st.divider()
st.caption(f"寻星配置跟踪系统 · V4 · {datetime.now().strftime('%H:%M:%S')}")
