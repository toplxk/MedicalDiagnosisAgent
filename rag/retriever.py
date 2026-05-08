from rag.query_rewriter import rewrite_query
from rag.vector_store import query as chroma_query
from config import RAG_TOP_K


def retrieve(query_text: str, top_k: int = None) -> dict:
    """RAG检索入口：查询改写 → 向量检索 → 返回结果。

    Args:
        query_text: 用户原始查询
        top_k: 返回结果数量

    Returns:
        {
            "original_query": 原始查询,
            "rewritten_query": 改写后的查询,
            "keywords": 关键词列表,
            "results": 检索结果列表,
            "context": 拼接后的上下文文本
        }
    """
    top_k = top_k or RAG_TOP_K

    # Step 1: 查询改写
    rewrite_result = rewrite_query(query_text)
    rewritten_query = rewrite_result.get("rewritten_query", query_text)
    keywords = rewrite_result.get("keywords", [])

    # Step 2: 使用改写后的查询 + 关键词进行检索
    # 合并改写查询和关键词进行多路检索
    search_texts = [rewritten_query] + keywords[:2]  # 最多用3个查询
    all_results = {}

    for text in search_texts:
        results = chroma_query(text, n_results=top_k)
        for r in results:
            doc_id = r["id"]
            if doc_id not in all_results or r["distance"] < all_results[doc_id]["distance"]:
                all_results[doc_id] = r

    # 按距离排序，取top_k
    sorted_results = sorted(all_results.values(), key=lambda x: x["distance"])[:top_k]

    # Step 3: 拼接上下文
    context_parts = []
    for i, r in enumerate(sorted_results, 1):
        source = r.get("metadata", {}).get("source", "未知来源")
        context_parts.append(f"[参考文档{i}] (来源: {source})\n{r['document']}")

    context = "\n\n---\n\n".join(context_parts) if context_parts else ""

    return {
        "original_query": query_text,
        "rewritten_query": rewritten_query,
        "keywords": keywords,
        "results": sorted_results,
        "context": context,
    }
