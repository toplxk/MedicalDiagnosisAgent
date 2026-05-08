import dashscope
from config import DASHSCOPE_API_KEY, EMBEDDING_MODEL


def get_embedding(text: str) -> list[float]:
    """使用千问Embedding模型获取文本的向量表示。

    Args:
        text: 要嵌入的文本

    Returns:
        文本的向量表示
    """
    dashscope.api_key = DASHSCOPE_API_KEY
    response = dashscope.TextEmbedding.call(
        model=EMBEDDING_MODEL,
        input=text,
    )
    if response.status_code == 200:
        return response.output["embeddings"][0]["embedding"]
    else:
        raise RuntimeError(f"Embedding调用失败: {response.code} - {response.message}")


def get_embeddings(texts: list[str], batch_size: int = 10) -> list[list[float]]:
    """批量获取文本的向量表示（自动分批，每批最多10条）。

    Args:
        texts: 文本列表
        batch_size: 每批处理数量，最大10

    Returns:
        向量列表
    """
    dashscope.api_key = DASHSCOPE_API_KEY
    batch_size = min(batch_size, 10)
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = dashscope.TextEmbedding.call(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        if response.status_code == 200:
            embeddings = [item["embedding"] for item in response.output["embeddings"]]
            all_embeddings.extend(embeddings)
        else:
            raise RuntimeError(f"Embedding调用失败: {response.code} - {response.message}")

    return all_embeddings
