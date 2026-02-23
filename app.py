"""
寻星市场情报中心 - 主页
"""
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="寻星市场情报中心", page_icon="🔭", layout="wide")

# 侧边栏
with st.sidebar:
    st.title("🔭 寻星情报中心")
    st.caption("Xunxing Market Intelligence")
    st.divider()
    st.markdown(f"📅 {datetime.now().strftime('%Y-%m-%d %A')}")
    st.divider()

    api_key = ""
    try:
        api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    except Exception:
        pass

    if api_key and not api_key.startswith("sk-xxxx"):
        st.success("🤖 AI引擎: 已连接")
    else:
        st.warning("🤖 AI引擎: 未配置")
        st.caption("Settings > Secrets 中配置 DEEPSEEK_API_KEY")

    st.divider()
    st.caption("⚠️ 仅供参考，不构成投资建议")

# 主页
st.title("🔭 寻星市场情报中心")
st.markdown("**Xunxing Market Intelligence Center** · Phase 1")
st.divider()

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("### 📰 资讯中心")
    st.markdown("财联社电报 + 东财新闻\n\nAI自动分类、情感分析、行业关联")

with c2:
    st.markdown("### 📊 市场总览")
    st.markdown("指数行情 · 涨跌统计\n\n行业板块 · 宏观数据 · ETF")

with c3:
    st.markdown("### 📝 每日研报")
    st.markdown("AI综合分析报告\n\n配置建议 · 行业推荐 · 个股线索")

st.divider()

st.markdown("👈 **通过左侧导航栏进入各模块**")

st.divider()

with st.expander("⚙️ 部署配置指南"):
    st.markdown("""
**1. DeepSeek API 配置（启用AI分析必须）**
1. 访问 [platform.deepseek.com](https://platform.deepseek.com/) 注册
2. 创建 API Key，充值10元
3. Streamlit Cloud → Settings → Secrets：
```toml
DEEPSEEK_API_KEY = "sk-你的密钥"
```

**2. 数据源**：AKShare + 财联社 均为免费，无需配置。
    """)
