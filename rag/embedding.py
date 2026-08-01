from langchain_community.embeddings import DashScopeEmbeddings
from config import DASHSCOPE_API_KEY, EMBEDDING_MODEL


def get_embedding(text: str) -> list[float]:
    """使用千问Embedding模型获取文本的向量表示。

    Args:
        text: 要嵌入的文本

    Returns:
        文本的向量表示
    """
    embeddings_model = DashScopeEmbeddings(
        model=EMBEDDING_MODEL,
        dashscope_api_key=DASHSCOPE_API_KEY,
    )
    try:
        return embeddings_model.embed_query(text)
    except Exception as e:
        raise RuntimeError(f"Embedding调用失败: {e}")


def get_embeddings(texts: list[str], batch_size: int = 10) -> list[list[float]]:
    """批量获取文本的向量表示（自动分批，每批最多10条）。

    Args:
        texts: 文本列表
        batch_size: 每批处理数量，最大10

    Returns:
        向量列表
    """
    embeddings_model = DashScopeEmbeddings(
        model=EMBEDDING_MODEL,
        dashscope_api_key=DASHSCOPE_API_KEY,
    )
    batch_size = min(batch_size, 10)
    all_embeddings = []

    try:
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = embeddings_model.embed_documents(batch)
            all_embeddings.extend(batch_embeddings)
    except Exception as e:
        raise RuntimeError(f"Embedding调用失败: {e}")

    return all_embeddings
