import json
from utils.llm_client import chat

REWRITE_SYSTEM_PROMPT = """你是一个医疗查询改写专家。你的任务是将用户的原始查询改写为更适合向量检索的形式。

改写规则：
1. 提取查询中的核心医疗关键词
2. 扩展相关的医学同义词和近义词
3. 将口语化表述转换为更专业的表述
4. 去除无关的修饰词
5. 如果是症状描述，补充可能涉及的医学术语

输出格式（严格JSON，不要输出其他内容）：
{
  "rewritten_query": "改写后的查询文本",
  "keywords": ["关键词1", "关键词2", ...],
  "expanded_terms": ["扩展术语1", "扩展术语2", ...]
}
"""


def rewrite_query(user_query: str) -> dict:
    """使用LLM对用户查询进行改写，以提升RAG检索效果。

    Args:
        user_query: 用户原始查询

    Returns:
        包含 rewritten_query, keywords, expanded_terms 的字典
    """
    messages = [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": f"请改写以下查询：{user_query}"},
    ]

    response = chat(messages, temperature=0.3)

    try:
        # 尝试从响应中提取JSON
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(response[json_start:json_end])
            return result
    except (json.JSONDecodeError, KeyError):
        pass

    # 解析失败时返回原始查询
    return {
        "rewritten_query": user_query,
        "keywords": [user_query],
        "expanded_terms": [],
    }
