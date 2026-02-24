"""
寻星市场情报中心 V4 - 主页
================================================================
V4: 登录认证 + Tushare PRO 优先 + 桥水式驾驶舱 + CIO日报严谨升级
================================================================
"""
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="寻星市场情报中心", page_icon="🔭", layout="wide")


# ============================================================
# 登录认证
# ============================================================
def check_login():
    """简单登录认证"""
    if st.session_state.get("authenticated"):
        return True

    st.markdown("""
    <div style="display:flex; justify-content:center; align-items:center; min-height:55vh;">
    <div style="width:400px; padding:40px; border-radius:16px;
    background: linear-gradient(135deg, rgba(255,107,53,0.08), rgba(69,183,209,0.04));
    border: 1px solid rgba(255,107,53,0.15); text-align:center;">
    <h1 style="margin:0 0 8px;">🔭</h1>
    <h2 style="margin:0 0 4px; color:#FF6B35;">寻星市场情报中心</h2>
    <p style="margin:0 0 24px; color:#888; font-size:14px;">Xunxing Market Intelligence · V4</p>
    </div></div>
    """, unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1, 1.5, 1])
    with col_c:
        with st.form("login_form"):
            username = st.text_input("用户名", placeholder="请输入用户名")
            password = st.text_input("密码", type="password", placeholder="请输入密码")
            submit = st.form_submit_button("🔐 登录", use_container_width=True, type="primary")
            if submit:
                valid_user = "admin"
                valid_pass = "281699"
                try:
                    valid_user = st.secrets.get("LOGIN_USER", "admin")
                    valid_pass = st.secrets.get("LOGIN_PASS", "281699")
                except Exception:
                    pass
                if username == valid_user and password == valid_pass:
                    st.session_state.authenticated = True
                    st.session_state.login_user = username
                    st.rerun()
                else:
                    st.error("❌ 用户名或密码错误")
    return False


if not check_login():
    st.stop()

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.title("🔭 寻星情报中心")
    st.caption("Xunxing Market Intelligence · V4")
    st.divider()
    st.markdown(f"📅 {datetime.now().strftime('%Y-%m-%d %A')}")
    st.markdown(f"👤 {st.session_state.get('login_user', 'admin')}")
    st.divider()

    api_key = ""
    try:
        api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    except Exception:
        pass
    if api_key and not api_key.startswith("sk-xxxx"):
        st.success("🤖 AI引擎: DeepSeek ✅")
    else:
        st.warning("🤖 AI引擎: 未配置")

    ts_token = ""
    try:
        ts_token = st.secrets.get("TUSHARE_TOKEN", "")
    except Exception:
        pass
    if ts_token:
        st.success("📡 主数据源: Tushare PRO ✅")
    else:
        st.warning("📡 数据源: 仅 AKShare (降级)")

    st.divider()
    if st.button("🚪 退出登录", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()
    st.caption("⚠️ 仅供参考，不构成投资建议")

# ============================================================
# 主页
# ============================================================
st.title("🔭 寻星市场情报中心")
st.markdown("**Xunxing Market Intelligence Center** · V4 · FOF CIO 决策平台")
st.divider()

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("""
    ### 📰 资讯雷达
    Tushare PRO 8源 + 新闻联播

    AI分类 · 情感分析 · 主线提炼
    """)
    st.page_link("pages/1_News.py", label="👉 进入资讯雷达", icon="📰", use_container_width=True)

with col2:
    st.markdown("""
    ### 📊 FOF 驾驶舱
    桥水式宏观 · 全维度扫描

    增长/通胀/流动性/信用 · 情绪
    """)
    st.page_link("pages/2_Market.py", label="👉 进入驾驶舱", icon="📊", use_container_width=True)

with col3:
    st.markdown("""
    ### 📝 CIO 日报
    AI 配置报告 · 全量数据驱动

    大类配置 · FOF策略 · 风控
    """)
    st.page_link("pages/3_Report.py", label="👉 进入 CIO 日报", icon="📝", use_container_width=True)

with col4:
    st.markdown("""
    ### 📈 量化选股
    多因子模型 · 三维共振

    量价 × 资金 × 技术 · AI点评
    """)
    st.page_link("pages/4_Quant.py", label="👉 进入量化选股", icon="📈", use_container_width=True)

st.divider()

with st.expander("🆕 V4 升级内容", expanded=False):
    st.markdown("""
**V4 核心升级**
- ✅ 登录认证系统 (可通过 Secrets 自定义凭据)
- ✅ **Tushare PRO 优先** → AKShare 降级兜底 数据架构
- ✅ 桥水式宏观仪表盘: 增长/通胀/流动性/信用 四维框架
- ✅ 波动率指标 · 市场宽度 · 情绪温度计 · 信用利差
- ✅ 风格动量扩展至20日中期趋势
- ✅ CIO 日报数据严谨性升级 (15+ 数据维度全量输入)
- ✅ 新闻采集优化: 默认150条 · 时间衰减权重
- ✅ **量化选股模型**: 8因子打分 · 三维共振 · AI深度点评

**V3 已有功能**
- ✅ 8源新闻并行采集 + 新闻联播
- ✅ 融资融券 / 北向资金 / 商品期货
- ✅ 券商研报评级 · FOF策略权重 · 大类配置
    """)

with st.expander("⚙️ 部署配置指南"):
    st.markdown("""
**必选: DeepSeek API**
```toml
DEEPSEEK_API_KEY = "sk-你的密钥"
```
**必选: Tushare PRO**
```toml
TUSHARE_TOKEN = "你的token"
```
**可选: 登录凭据 (默认 admin/281699)**
```toml
LOGIN_USER = "admin"
LOGIN_PASS = "281699"
```
    """)

st.caption("💡 首次加载需10-30秒，缓存后会快很多。")
