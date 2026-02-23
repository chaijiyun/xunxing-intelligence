"""
📝 每日研报 - AI综合分析
"""
import streamlit as st
import json
import os
from datetime import datetime
import pandas as pd
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_fetcher import (
    get_major_indices, get_market_overview, get_industry_board,
    get_macro_data, get_style_data, get_cls_telegraph,
)
from utils.ai_analyzer import analyze_news_batch, generate_daily_report

st.set_page_config(page_title="每日研报", page_icon="📝", layout="wide")
st.title("📝 每日研报")
st.caption("AI 综合分析 · 宏观判断 · 配置建议 · 投资线索")
st.divider()

# API检查
api_key = ""
try:
    api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
except Exception:
    pass
has_api = bool(api_key and not api_key.startswith("sk-xxxx"))

if not has_api:
    st.warning("""
⚠️ **未配置 DeepSeek API Key** — 研报需要AI能力

1. 注册 [platform.deepseek.com](https://platform.deepseek.com/)
2. 创建 API Key，充值10元
3. Streamlit Cloud → Settings → Secrets 添加：
```
DEEPSEEK_API_KEY = "sk-你的密钥"
```
    """)

# 缓存
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
    st.info(f"📄 已有今日缓存报告（{cached.get('time', '')}）")

c1, c2 = st.columns(2)
with c1:
    gen_btn = st.button("🚀 生成新报告", type="primary", use_container_width=True, disabled=not has_api)
with c2:
    load_btn = st.button("📄 查看缓存", use_container_width=True, disabled=not cached)

report = None

if gen_btn and has_api:
    progress = st.progress(0, "准备中...")

    # 采集
    progress.progress(10, "📡 采集行情...")
    idx_df = get_major_indices()
    overview = get_market_overview()
    style = get_style_data()
    macro = get_macro_data()
    ind_df = get_industry_board()

    progress.progress(30, "📰 采集资讯...")
    news = get_cls_telegraph(50)

    progress.progress(50, "🤖 AI分析资讯...")
    analyzed = analyze_news_batch(news)

    # 构造摘要
    progress.progress(70, "📝 生成报告...")

    # 市场摘要
    market_parts = ["## 市场数据"]
    if idx_df is not None and not idx_df.empty and "error" not in idx_df.columns:
        for _, r in idx_df.iterrows():
            chg = r.get("涨跌幅", 0)
            chg_str = f"{chg:+.2f}%" if pd.notna(chg) else ""
            market_parts.append(f"- {r.get('名称','')}: {r.get('最新价','')} ({chg_str})")

    if overview and "error" not in overview:
        market_parts.append(f"\n涨{overview.get('上涨',0)} 跌{overview.get('下跌',0)} "
                            f"涨停{overview.get('涨停',0)} 跌停{overview.get('跌停',0)} "
                            f"成交{overview.get('总成交额亿',0)}亿")

    if style:
        market_parts.append(f"\n风格: {style.get('偏好','')} | "
                            f"沪深300 5日{style.get('沪深300_5日','')}% | "
                            f"中证1000 5日{style.get('中证1000_5日','')}%")

    if macro:
        market_parts.append("\n宏观: " + " | ".join(f"{k}:{v}" for k, v in macro.items()))

    if ind_df is not None and not ind_df.empty:
        top5 = ind_df.head(5)
        if "板块名称" in top5.columns and "涨跌幅" in top5.columns:
            market_parts.append("\n行业涨幅前5: " +
                                ", ".join(f"{r['板块名称']}({r['涨跌幅']:+.1f}%)" for _, r in top5.iterrows()))
        bot5 = ind_df.tail(5)
        if "板块名称" in bot5.columns and "涨跌幅" in bot5.columns:
            market_parts.append("行业跌幅前5: " +
                                ", ".join(f"{r['板块名称']}({r['涨跌幅']:+.1f}%)" for _, r in bot5.iterrows()))

    market_text = "\n".join(market_parts)

    # 资讯摘要
    news_parts = ["## 今日资讯"]
    if analyzed:
        sents = [item.get("analysis", {}).get("sentiment", 0) for item in analyzed]
        avg = sum(sents) / len(sents) if sents else 0
        news_parts.append(f"共{len(analyzed)}条, 整体情绪{avg:.2f}")

        sorted_news = sorted(analyzed, key=lambda x: x.get("analysis", {}).get("impact", 0), reverse=True)
        for item in sorted_news[:20]:
            a = item.get("analysis", {})
            s = a.get("sentiment", 0)
            emoji = "🟢" if s > 0.2 else ("🔴" if s < -0.2 else "⚪")
            secs = ",".join(a.get("sectors", []))
            news_parts.append(f"{emoji}[{a.get('category','')}] {item.get('title','')} | {s:+.2f} | {secs}")

    news_text = "\n".join(news_parts)

    # 调用AI
    report = generate_daily_report(market_text, news_text)

    progress.progress(90, "💾 保存...")
    save_cache({"time": datetime.now().strftime("%H:%M"), "report": report})

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
background: linear-gradient(135deg, rgba(255,107,53,0.1), rgba(69,183,209,0.05));
border: 1px solid rgba(255,107,53,0.2); margin-bottom:20px;">
<h2 style="margin:0; color:#FF6B35;">寻星市场日报</h2>
<p style="margin:4px 0 0; color:#999;">{datetime.now().strftime('%Y年%m月%d日')} · DeepSeek V3</p>
</div>""", unsafe_allow_html=True)

    st.markdown(report)

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("📄 下载 Markdown", report,
                           f"寻星日报_{datetime.now().strftime('%Y%m%d')}.md",
                           "text/markdown", use_container_width=True)
    with c2:
        st.download_button("📝 下载 TXT",
                           report.replace("###", "").replace("**", ""),
                           f"寻星日报_{datetime.now().strftime('%Y%m%d')}.txt",
                           "text/plain", use_container_width=True)
else:
    if not gen_btn:
        st.markdown("""
### 报告将包含：

| 章节 | 内容 | 对应需求 |
|------|------|----------|
| 宏观环境 | 股债商配置倾向 | 大类资产方向 |
| 风格研判 | 大小盘/成长价值 | FOF风格产品增减配 |
| 行业推荐 | TOP3行业+回避 | ETF配置+选股方向 |
| FOF建议 | 各策略增减配 | 寻星组合调整 |
| ETF推荐 | 具体代码+逻辑 | ETF替代仓位 |
| 个股线索 | 机会+催化剂 | 个人投资 |
| 风险提示 | 主要风险点 | 防御配置 |

👆 点击 **「生成新报告」** 开始
        """)

st.caption(f"寻星配置跟踪系统 · v1.0")
