"""
寻星市场情报中心 V2 - 主页
"""
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="寻星市场情报中心", page_icon="🔭", layout="wide")

# 侧边栏
with st.sidebar:
    st.title("🔭 寻星情报中心")
    st.caption("Xunxing Market Intelligence · V3")
    st.divider()
    st.markdown(f"📅 {datetime.now().strftime('%Y-%m-%d %A')}")
    st.divider()

    # DeepSeek API 状态
    api_key = ""
    try:
        api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    except Exception:
        pass
    if api_key and not api_key.startswith("sk-xxxx"):
        st.success("🤖 AI引擎: DeepSeek ✅")
    else:
        st.warning("🤖 AI引擎: 未配置")
        st.caption("Secrets 中配置 DEEPSEEK_API_KEY")

    # Tushare PRO 状态
    ts_token = ""
    try:
        ts_token = st.secrets.get("TUSHARE_TOKEN", "")
    except Exception:
        pass
    if ts_token:
        st.success("📡 数据源: Tushare PRO ✅")
    else:
        st.warning("📡 数据源: 仅 AKShare + 新浪")
        st.caption("Secrets 中配置 TUSHARE_TOKEN 升级数据质量")

    st.divider()
    st.caption("⚠️ 仅供参考，不构成投资建议")

# 主页
st.title("🔭 寻星市场情报中心")
st.markdown("**Xunxing Market Intelligence Center** · V3 · FOF CIO 决策平台")
st.divider()

# 导航卡片
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    ### 📰 资讯雷达
    Tushare PRO 新闻 + 新浪快讯

    AI分类 · 情感分析 · 核心主线提炼
    """)
    st.page_link("pages/1_News.py", label="👉 进入资讯雷达", icon="📰", use_container_width=True)

with col2:
    st.markdown("""
    ### 📊 FOF 驾驶舱
    宏观 · 风格 · 资金 · 期货 · 板块

    北向资金 · 融资融券 · 券商研报 · ETF
    """)
    st.page_link("pages/2_Market.py", label="👉 进入驾驶舱", icon="📊", use_container_width=True)

with col3:
    st.markdown("""
    ### 📝 CIO 日报
    AI 综合配置报告

    大类配置 · FOF策略权重 · 行业 · ETF
    """)
    st.page_link("pages/3_Report.py", label="👉 进入 CIO 日报", icon="📝", use_container_width=True)

st.divider()

# V2 升级说明
with st.expander("🆕 V3 升级内容", expanded=False):
    st.markdown("""
**数据源升级 (V3 新增)**
- ✅ Tushare PRO 券商研报: 评级变动 + 目标价
- ✅ 融资融券余额: 杠杆情绪监控
- ✅ 商品期货行情: 黄金/原油/铜/螺纹钢等 (CTA策略参考)
- ✅ 人民币汇率追踪
- ✅ 全量数据打包引擎 (12个数据模块一次性采集)

**AI 分析升级**
- ✅ FOF CIO 专用 Prompt 框架 — 强制输出结构化配置比例
- ✅ 大类资产权重 (权益/固收/商品/现金 = 100%)
- ✅ FOF策略权重 (多头/指增500/指增1000/中性/CTA/套利/固收+ = 100%)
- ✅ 环境-策略适配逻辑 (趋势市/震荡市/高波动 → 策略偏好)
- ✅ 券商研报动态纳入 AI 分析输入

**架构优化**
- ✅ 驾驶舱新增: 资金流向面板 + 商品期货面板 + 券商研报Tab
- ✅ 数据打包→文本转化→AI生成 三段式流水线
- ✅ Tushare PRO 连接状态实时监测
    """)

with st.expander("⚙️ 部署配置指南"):
    st.markdown("""
**必选: DeepSeek API (AI分析引擎)**
```toml
DEEPSEEK_API_KEY = "sk-你的密钥"
```

**强烈推荐: Tushare PRO (主力数据源)**
1. 注册 [tushare.pro](https://tushare.pro/)
2. 获取 Token (个人主页 → 接口TOKEN)
3. Streamlit Cloud → Settings → Secrets:
```toml
TUSHARE_TOKEN = "你的token"
```

**数据源**: AKShare(免费) + Tushare PRO(推荐) + 新浪快讯(备用)
    """)

st.caption("💡 **首次加载**: 海外服务器访问国内数据源需10-30秒，缓存后会快很多。")
