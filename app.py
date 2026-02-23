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

# ============================================================
# 可点击的导航卡片
# ============================================================
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    ### 📰 资讯中心
    财联社电报 + 东财新闻

    AI自动分类 · 情感分析 · 行业关联
    """)
    st.page_link("pages/1_News.py", label="👉 进入资讯中心", icon="📰", use_container_width=True)

with col2:
    st.markdown("""
    ### 📊 市场总览
    指数行情 · 涨跌统计

    行业板块 · 宏观数据 · ETF
    """)
    st.page_link("pages/2_Market.py", label="👉 进入市场总览", icon="📊", use_container_width=True)

with col3:
    st.markdown("""
    ### 📝 每日研报
    AI综合分析报告

    配置建议 · 行业推荐 · 个股线索
    """)
    st.page_link("pages/3_Report.py", label="👉 进入每日研报", icon="📝", use_container_width=True)

st.divider()

st.caption("💡 **关于加载速度**：Streamlit Cloud 服务器在海外，首次访问国内数据源需要10-30秒，数据缓存后会快很多。")

st.divider()

with st.expander("⚙️ 部署配置指南"):
    st.markdown("""
**DeepSeek API 配置（启用AI分析必须）**
1. 注册 [platform.deepseek.com](https://platform.deepseek.com/)
2. 创建 API Key，充值10元
3. Streamlit Cloud → Settings → Secrets：
```toml
DEEPSEEK_API_KEY = "sk-你的密钥"
```

**数据源**：AKShare + 财联社 均为免费，无需配置。
    """)
