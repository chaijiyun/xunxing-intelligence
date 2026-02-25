"""
寻星市场情报中心 V4.1 - 主页 (集成二波雷达，剥离明文配置)
================================================================
V4.1: 登录认证 + Tushare PRO 优先 + 桥水式驾驶舱 + 二波配置雷达
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
    <p style="margin:0 0 24px; color:#888; font-size:14px;">Xunxing Market Intelligence · V4.1</p>
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
    st.caption("Xunxing Market Intelligence · V4.1")
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
# 主页网格导航 (3x2 架构)
# ============================================================
st.title("🔭 寻星市场情报中心")
st.markdown("**Xunxing Market Intelligence Center** · V4.1 · FOF CIO 决策平台")
st.divider()

# 第一排导航
col1, col2, col3 = st.columns(3)

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

st.write("") # 增加排版间距

# 第二排导航
col4, col5, col6 = st.columns(3)

with col4:
    st.markdown("""
    ### 📈 量化选股
    多因子模型 · 三维共振

    量价 × 资金 × 技术 · AI点评
    """)
    st.page_link("pages/4_Quant.py", label="👉 进入量化选股", icon="📈", use_container_width=True)

with col5:
    st.markdown("""
    ### 🎯 二波配置雷达
    中线配置 · 强势回调狙击

    市值基本面 × 极度缩量形态
    """)
    st.page_link("pages/5_Pullback.py", label="👉 进入二波雷达", icon="🎯", use_container_width=True)

with col6:
    st.markdown("""
    ### 🛠️ 系统自检与扩展
    (架构师预留位)

    数据管道监控 · 核心指标校准
    """)
    st.button("⚙️ 模块开发中...", disabled=True, use_container_width=True)

st.divider()

# ============================================================
# 系统更新日志 
# ============================================================
with st.expander("🆕 V4.1 升级内容 (当前版本)", expanded=False):
    st.markdown("""
**V4.1 架构师重构**
- ✅ **核心逻辑修复**：量价因子计算底层强制切入前复权(qfq)流，消灭除权价格失真。
- ✅ **新增模块**：[5_Pullback] 二波配置雷达，结合 PE 估值与缩量回调形态的中线狙击系统。
- ✅ **UI 重构**：主页入口改为 3x2 网格，剥离底层配置显示，增强系统黑盒隐匿性。
- ✅ 桥水式宏观仪表盘: 增长/通胀/流动性/信用 四维框架。
- ✅ CIO 日报数据严谨性升级 (15+ 数据维度全量输入)。
    """)

st.caption("💡 架构师提示：量化引擎的核心是数据的绝对纯净。复权数据切入完毕，系统算力已就绪。")