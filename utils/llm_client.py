import dashscope
from dashscope import Generation
from config import QIANWEN_API_KEY, LLM_MODEL


def chat(messages: list[dict], model: str = None, temperature: float = 0.7) -> str:
    """调用千问大模型进行对话（非流式）。"""
    dashscope.api_key = QIANWEN_API_KEY
    response = Generation.call(
        model=model or LLM_MODEL,
        messages=messages,
        temperature=temperature,
        result_format="message",
    )
    if response.status_code == 200:
        return response.output.choices[0].message.content
    else:
        return f"[LLM调用失败] {response.code}: {response.message}"


def chat_stream(messages: list[dict], model: str = None, temperature: float = 0.7):
    """调用千问大模型进行流式对话。

    Yields:
        每个token的文本片段
    """
    dashscope.api_key = QIANWEN_API_KEY
    responses = Generation.call(
        model=model or LLM_MODEL,
        messages=messages,
        temperature=temperature,
        result_format="message",
        stream=True,
        incremental_output=True,
    )
    for response in responses:
        if response.status_code == 200:
            content = response.output.choices[0].message.content
            if content:
                yield content
        else:
            yield f"\n[LLM调用失败] {response.code}: {response.message}"
            break


def chat_with_system(system_prompt: str, user_message: str, history: list[dict] = None,
                     temperature: float = 0.7) -> str:
    """带系统提示词的对话调用。"""
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return chat(messages, temperature=temperature)
