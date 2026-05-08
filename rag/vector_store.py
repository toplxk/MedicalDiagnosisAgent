import os
import chromadb
from chromadb.config import Settings
from config import CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME
from rag.embedding import get_embedding, get_embeddings


_client = None
_collection = None


def _get_collection():
    """获取或创建Chroma集合（懒加载）。"""
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_documents(documents: list[str], metadatas: list[dict] = None, ids: list[str] = None):
    """将文档添加到向量数据库。

    Args:
        documents: 文档文本列表
        metadatas: 元数据列表
        ids: 文档ID列表
    """
    collection = _get_collection()

    if ids is None:
        existing = collection.count()
        ids = [f"doc_{existing + i}" for i in range(len(documents))]

    embeddings = get_embeddings(documents)

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas or [{}] * len(documents),
    )


def query(query_text: str, n_results: int = 3) -> list[dict]:
    """检索与查询最相关的文档。

    Args:
        query_text: 查询文本
        n_results: 返回结果数量

    Returns:
        检索结果列表，每项包含 document, metadata, distance
    """
    collection = _get_collection()

    if collection.count() == 0:
        return []

    query_embedding = get_embedding(query_text)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    items = []
    for i in range(len(results["ids"][0])):
        items.append({
            "id": results["ids"][0][i],
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })

    return items


def get_collection_count() -> int:
    """返回集合中的文档数量。"""
    return _get_collection().count()


def clear_collection():
    """清空集合。"""
    global _client, _collection
    if _client is not None:
        try:
            _client.delete_collection(CHROMA_COLLECTION_NAME)
        except Exception:
            pass
    _collection = None
