"""
AI 分析模块 - DeepSeek API
"""
import json
import streamlit as st
from datetime import datetime

def _get_api_key() -> str:
    try:
        key = st.secrets.get("DEEPSEEK_API_KEY", "")
        if key and not key.startswith("sk-xxxx"):
            return key
    except Exception:
        pass
    return ""

def _call_deepseek(prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 4000) -> str:
    """调用 DeepSeek V3"""
    api_key = _get_api_key()
    if not api_key:
        return ""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[AI调用失败: {e}]"

# ============================================================
# 资讯批量分析
# ============================================================
def analyze_news_batch(news_list: list) -> list:
    """批量分析资讯"""
    if not news_list:
        return []

    api_key = _get_api_key()
    if not api_key:
        return _keyword_analysis(news_list)

    results = []
    batch_size = 10
    for i in range(0, len(news_list), batch_size):
        batch = news_list[i:i + batch_size]

        batch_text = ""
        for idx, item in enumerate(batch):
            batch_text += f"\n[{idx+1}] {item.get('title','')}\n"

        prompt = f"""分析以下{len(batch)}条A股财经资讯，返回JSON数组。
每条包含：id(序号), category(宏观/行业/公司/海外/政策), sentiment(-1到1), impact(1-5), sectors(相关行业数组), summary(15字摘要)

资讯：
{batch_text}

直接返回JSON数组，不要其他文字："""

        resp = _call_deepseek(prompt, "你是A股金融分析师，只返回JSON", temperature=0.1, max_tokens=2000)

        parsed = _parse_json(resp)
        if parsed:
            for item in parsed:
                idx = item.get("id", 0) - 1
                if 0 <= idx < len(batch):
                    batch[idx]["analysis"] = item
            results.extend(batch)
        else:
            results.extend(_keyword_analysis(batch))

    return results

def _parse_json(text: str):
    if not text or text.startswith("[AI调用失败"):
        return None
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        r = json.loads(text)
        return r if isinstance(r, list) else [r]
    except Exception:
        s, e = text.find("["), text.rfind("]") + 1
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e])
            except Exception:
                pass
    return None

def _keyword_analysis(news_list: list) -> list:
    pos_words = ["利好", "上涨", "增长", "突破", "超预期", "创新高", "支持", "扩大"]
    neg_words = ["利空", "下跌", "下降", "低于预期", "收缩", "暴跌", "收紧", "风险"]
    cat_map = {
        "宏观": ["GDP", "CPI", "PPI", "PMI", "央行", "降准", "降息", "利率", "MLF", "社融", "两会"],
        "海外": ["美联储", "美国", "欧洲", "美股", "美债", "美元", "关税"],
        "政策": ["工信部", "发改委", "证监会", "国务院", "政策", "规划", "监管"],
        "行业": ["半导体", "芯片", "AI", "人工智能", "机器人", "新能源", "医药", "军工"],
    }
    sec_map = {
        "半导体": ["半导体", "芯片", "晶圆"],
        "AI": ["AI", "人工智能", "大模型", "算力", "机器人"],
        "新能源": ["新能源", "光伏", "锂电", "储能"],
        "医药": ["医药", "创新药", "GLP", "医疗"],
        "消费": ["消费", "白酒", "食品", "旅游"],
        "金融": ["银行", "券商", "保险"],
    }

    for item in news_list:
        text = item.get("title", "") + item.get("content", "")
        category = "公司"
        for cat, kws in cat_map.items():
            if any(k in text for k in kws):
                category = cat
                break

        pos = sum(1 for w in pos_words if w in text)
        neg = sum(1 for w in neg_words if w in text)
        sentiment = round(min(max((pos - neg) * 0.25, -1), 1), 2)
        sectors = [s for s, kws in sec_map.items() if any(k in text for k in kws)]

        item["analysis"] = {
            "category": category,
            "sentiment": sentiment,
            "impact": 3 if item.get("important") else 2,
            "sectors": sectors[:3],
            "summary": item.get("title", "")[:15],
        }

    return news_list

def generate_daily_report(market_text: str, news_text: str) -> str:
    api_key = _get_api_key()
    if not api_key:
        return "⚠️ 未配置 API Key。"

    system = """你是「寻星资产配置公司」的首席投资官（CIO）兼AI投研中枢。
    核心任务：为专业 FOF 管理人提供自上而下的资产配置决策。强调胜率与盈亏比，给出明确建议。"""

    prompt = f"""基于以下客观数据，生成 {datetime.now().strftime('%Y年%m月%d日')} 寻星市场日报。

【输入数据】
{market_text}
{news_text}

【报告框架要求】
### 🔭 一、 市场异动与宏观定调
### 🧭 二、 寻星大类资产配置时钟
### 🧩 三、 FOF 底层策略调仓指南
### 🎭 四、 A股结构与风格研判
### 🎯 五、 寻星战术工具箱 (ETF与个股)
### 🛡️ 六、 尾部风险与对冲预案
"""
    return _call_deepseek(prompt, system, temperature=0.4, max_tokens=4000)

def analyze_single_news(text: str) -> str:
    api_key = _get_api_key()
    if not api_key:
        return "请先配置 DeepSeek API Key"

    prompt = f"""深度分析以下资讯：\n{text}\n\n1.事件定性 2.影响范围 3.对资产影响 4.持续性 5.应对建议"""
    return _call_deepseek(prompt, temperature=0.3, max_tokens=2000)

# ============================================================
# 全局大势提炼 (核心主线提取)
# ============================================================
def summarize_market_threads(news_list: list) -> str:
    """提取数百条新闻中的核心投资主线"""
    api_key = _get_api_key()
    if not api_key or not news_list:
        return "⚠️ 未配置 API 密钥或无资讯数据。"

    # 将所有新闻浓缩为纯文本
    text_blocks = [f"- {n.get('title','')} {n.get('content','')[:50]}" for n in news_list]
    news_text = "\n".join(text_blocks)

    system = """你是寻星资产配置公司的 CIO。你的任务是从一堆碎片化资讯中，提炼出当前市场最具爆发力的投资主线。
    绝不要流水账罗列新闻，必须寻找群体性、行业性或宏观级别的事件共振。"""

    prompt = f"""基于以下 {len(news_list)} 条最新清洗后的市场资讯，为你提炼出当前市场最核心的 3 条投资主线或宏观异动。
    
    【格式要求】（直接输出 Markdown 格式）
    ### 🔥 市场核心主线提炼
    1. **[主线名称/板块]**：(一句话解释背后的催化剂事件)
       - **配置思路**：(从FOF策略或ETF配置角度给出应对建议)
    2. ... (以此类推，必须写满 3 条)

    【输入资讯】
    {news_text}
    """
    # 扩大 max_tokens 防止被截断
    return _call_deepseek(prompt, system, temperature=0.3, max_tokens=2500)