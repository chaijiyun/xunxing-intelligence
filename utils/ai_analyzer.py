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

    # 分批处理, 每批10条
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
    """解析JSON响应"""
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
    """无API时关键词分析"""
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

        # 分类
        category = "公司"
        for cat, kws in cat_map.items():
            if any(k in text for k in kws):
                category = cat
                break

        # 情感
        pos = sum(1 for w in pos_words if w in text)
        neg = sum(1 for w in neg_words if w in text)
        sentiment = round(min(max((pos - neg) * 0.25, -1), 1), 2)

        # 行业
        sectors = [s for s, kws in sec_map.items() if any(k in text for k in kws)]

        item["analysis"] = {
            "category": category,
            "sentiment": sentiment,
            "impact": 3 if item.get("important") else 2,
            "sectors": sectors[:3],
            "summary": item.get("title", "")[:15],
        }

    return news_list


# ============================================================
# 每日报告生成
# ============================================================

def generate_daily_report(market_text: str, news_text: str) -> str:
    """生成每日综合报告"""
    api_key = _get_api_key()
    if not api_key:
        return "⚠️ 未配置 DeepSeek API Key，无法生成AI报告。\n\n请在 Streamlit Cloud Settings > Secrets 中配置：\n```\nDEEPSEEK_API_KEY = \"sk-你的密钥\"\n```"

    system = """你是「寻星配置跟踪系统」的AI投研顾问。用户是FOF管理人，同时做个人股票投资。
要求：专业简洁、观点明确、可操作、含风险提示。"""

    prompt = f"""基于以下数据生成{datetime.now().strftime('%Y年%m月%d日')}市场分析报告。

{market_text}

{news_text}

报告框架：
### 一、今日市场回顾
### 二、宏观环境与大类资产配置方向
（股票/债券/商品的配置倾向）
### 三、市场风格研判
（大盘vs小盘、成长vs价值）
### 四、行业方向推荐
（TOP3看好行业 + 回避行业）
### 五、FOF配置建议
（股票多头/量化/CTA/固收各自增减配建议）
### 六、ETF配置推荐
（3-5只ETF，含代码和逻辑）
### 七、个股投资线索
（3-5条机会，含催化剂）
### 八、风险提示"""

    return _call_deepseek(prompt, system, temperature=0.4, max_tokens=4000)


def analyze_single_news(text: str) -> str:
    """单条资讯深度分析"""
    api_key = _get_api_key()
    if not api_key:
        return "请先配置 DeepSeek API Key"

    prompt = f"""深度分析以下财经资讯：

{text}

从以下维度分析：
1. 事件定性
2. 影响范围（行业/公司）
3. 对股票/债券/商品的影响
4. 持续性（短期or中长期）
5. FOF配置和个人股票投资的应对建议"""

    return _call_deepseek(prompt, temperature=0.3, max_tokens=2000)
