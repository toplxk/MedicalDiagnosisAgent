from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from config import QIANWEN_API_KEY, LLM_MODEL


def _convert_messages(messages: list[dict]) -> list:
    """将 dict 格式消息转换为 LangChain Message 对象。"""
    lc_messages = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
    return lc_messages


def chat(messages: list[dict], model: str = None, temperature: float = 0.7) -> str:
    """调用千问大模型进行对话（非流式）。"""
    llm = ChatTongyi(
        model=model or LLM_MODEL,
        dashscope_api_key=QIANWEN_API_KEY,
        temperature=temperature,
    )
    lc_messages = _convert_messages(messages)
    try:
        response = llm.invoke(lc_messages)
        return response.content
    except Exception as e:
        return f"[LLM调用失败] {e}"


def chat_stream(messages: list[dict], model: str = None, temperature: float = 0.7):
    """调用千问大模型进行流式对话。

    Yields:
        每个token的文本片段
    """
    llm = ChatTongyi(
        model=model or LLM_MODEL,
        dashscope_api_key=QIANWEN_API_KEY,
        temperature=temperature,
        streaming=True,
    )
    lc_messages = _convert_messages(messages)
    try:
        for chunk in llm.stream(lc_messages):
            content = chunk.content
            if content:
                yield content
    except Exception as e:
        yield f"\n[LLM调用失败] {e}"
