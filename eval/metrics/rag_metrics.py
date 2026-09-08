"""RAG 测评指标：检索层（Recall@k / Precision@k / Hit@k / MRR / nDCG@k）
与生成层（Keypoint Coverage）。

pred_ids 为检索返回的 chunk_id 列表（按排名）；gold_ids 为标注的黄金 chunk_id 列表。
"""
import re
from collections import defaultdict


def hit_set(pred_ids: list[str], gold_ids: set, k: int) -> bool:
    return bool(gold_ids & set(pred_ids[:k]))


def recall_at_k(pred_ids_list: list[list[str]], gold_ids_list: list[list[str]], k: int) -> float:
    """Recall@k = 命中的 gold 数 / gold 总数，全样本平均。"""
    if not gold_ids_list:
        return 0.0
    recalls = []
    for pred, gold in zip(pred_ids_list, gold_ids_list):
        gold_set = set(gold)
        if not gold_set:
            continue
        hit = len(gold_set & set(pred[:k]))
        recalls.append(hit / len(gold_set))
    return sum(recalls) / len(recalls) if recalls else 0.0


def precision_at_k(pred_ids_list: list[list[str]], gold_ids_list: list[list[str]], k: int) -> float:
    """Precision@k = 前 k 结果中命中的比例，全样本平均。"""
    if not pred_ids_list:
        return 0.0
    precisions = []
    for pred, gold in zip(pred_ids_list, gold_ids_list):
        gold_set = set(gold)
        topk = pred[:k]
        if not topk:
            precisions.append(0.0)
            continue
        precisions.append(len(gold_set & set(topk)) / len(topk))
    return sum(precisions) / len(precisions)


def hit_at_k(pred_ids_list: list[list[str]], gold_ids_list: list[list[str]], k: int) -> float:
    """Hit@k = 至少命中一个 gold 的样本比例。"""
    if not gold_ids_list:
        return 0.0
    hits = [hit_set(p, set(g), k) for p, g in zip(pred_ids_list, gold_ids_list)]
    return sum(hits) / len(hits)


def mrr(pred_ids_list: list[list[str]], gold_ids_list: list[list[str]]) -> float:
    """MRR = 平均 1/首个命中排名（排名从 1 开始）。"""
    if not gold_ids_list:
        return 0.0
    reciprocals = []
    for pred, gold in zip(pred_ids_list, gold_ids_list):
        gold_set = set(gold)
        rank = next((i + 1 for i, p in enumerate(pred) if p in gold_set), None)
        reciprocals.append(1 / rank if rank else 0.0)
    return sum(reciprocals) / len(reciprocals)


def ndcg_at_k(pred_ids_list: list[list[str]], gold_ids_list: list[list[str]], k: int,
              relevance: dict = None) -> float:
    """nDCG@k：二值相关度（relevance 可按 chunk_id 覆盖为分级相关度）。

    DCG = Σ rel_i / log2(i+1)（i 从 1 开始，只有 gold 命中才计入）；IDCG 取理想排序。
    """
    if not gold_ids_list:
        return 0.0
    import math

    ndcgs = []
    for pred, gold in zip(pred_ids_list, gold_ids_list):
        gold_set = set(gold)
        if not gold_set:
            continue
        dcg = 0.0
        for i, pid in enumerate(pred[:k]):
            if pid in gold_set:
                rel = relevance.get(pid, 1.0) if relevance else 1.0
                dcg += rel / math.log2(i + 2)
        rels = sorted(
            [relevance.get(g, 1.0) if relevance else 1.0 for g in gold], reverse=True
        )
        idcg = sum(r / math.log2(i + 2) for i, r in enumerate(rels[:k]))
        if idcg == 0.0:
            continue
        ndcgs.append(dcg / idcg)
    return sum(ndcgs) / len(ndcgs) if ndcgs else 0.0


def keypoint_coverage(answer: str, keypoints: list[dict]) -> float:
    """Keypoint Coverage：gold_keypoints 中被回答覆盖的比例。

    keypoints 为 [{"term": "低盐饮食", "aliases": ["低盐", "少盐"]}, ...]，
    任一别名出现在回答中即视为覆盖。
    """
    if not keypoints:
        return 1.0
    answer_lower = answer.lower()
    covered = 0
    for kp in keypoints:
        terms = [kp.get("term", "")] + kp.get("aliases", [])
        if any(term and term.lower() in answer_lower for term in terms):
            covered += 1
    return covered / len(keypoints)


def refusal_stats(results: list[dict]) -> dict:
    """负样本（库外问题）拒答统计。

    每条结果需含 "is_negative" (bool) 与 "refused" (bool, 是否表现出拒答/无依据回答)。
    返回 {"n": 负样本数, "refusal_rate": 正确拒答比例}。
    """
    negs = [r for r in results if r.get("is_negative")]
    if not negs:
        return {"n": 0, "refusal_rate": None}
    refused = sum(bool(r.get("refused")) for r in negs)
    return {"n": len(negs), "refusal_rate": refused / len(negs)}


def summarize_retrieval(pred_ids_list: list[list[str]], gold_ids_list: list[list[str]],
                        ks: list[int] = (1, 3, 5)) -> dict:
    """汇总检索层指标。"""
    summary = {"mrr": mrr(pred_ids_list, gold_ids_list)}
    for k in ks:
        summary[f"recall@{k}"] = recall_at_k(pred_ids_list, gold_ids_list, k)
        summary[f"precision@{k}"] = precision_at_k(pred_ids_list, gold_ids_list, k)
        summary[f"hit@{k}"] = hit_at_k(pred_ids_list, gold_ids_list, k)
        summary[f"ndcg@{k}"] = ndcg_at_k(pred_ids_list, gold_ids_list, k)
    return summary


def _self_test():
    """手工计算的自测用例。"""
    import math
    preds = [["c1", "c2", "c3"], ["c4", "c1"]]
    golds = [["c3"], ["c1", "c9"]]

    # 样本1：k=2 时命中(c3在top2)；k=3 命中1/1=1.0
    assert abs(recall_at_k(preds, golds, 2) - (0.0 + 0.5) / 2) < 1e-9   # 样本1: 0/1, 样本2: 1/2
    assert abs(recall_at_k(preds, golds, 3) - (1.0 + 0.5) / 2) < 1e-9
    # 样本2 top3 实为 2 条（pred[:3] 不补齐）→ 1/2
    assert abs(precision_at_k(preds, golds, 3) - (1 / 3 + 1 / 2) / 2) < 1e-9
    assert abs(hit_at_k(preds, golds, 2) - 0.5) < 1e-9    # 样本2在top2命中c1
    assert abs(hit_at_k(preds, golds, 3) - 1.0) < 1e-9
    # MRR: 样本1: c3 在 rank3 → 1/3; 样本2: c1 在 rank2 → 1/2; mean=5/12
    assert abs(mrr(preds, golds) - 5 / 12) < 1e-9

    # nDCG（手算）: 样本1 gold=[c3] pred=[c1,c2,c3] → DCG=1/log2(4)=0.5, IDCG=1 → 0.5
    assert abs(ndcg_at_k(preds, golds, 3) - (0.5 + 0.3869) / 2) < 1e-3
    # 样本2 gold=[c1,c9] pred=[c4,c1] → DCG=1/log2(3)=0.631, IDCG=1+0.631=1.631 → 0.3869
    assert abs(ndcg_at_k([["c4", "c1"]], [["c1", "c9"]], 3) - (1 / math.log2(3)) / (1 + 1 / math.log2(3))) < 1e-9

    # Keypoint: aliases 与 term 都能命中；answer 小写不敏感
    kps = [{"term": "低盐饮食", "aliases": ["少盐"]}, {"term": "戒烟", "aliases": []}]
    assert keypoint_coverage("建议低盐饮食", kps) == 0.5
    assert keypoint_coverage("建议低盐饮食并戒烟", kps) == 1.0

    # 拒答统计
    rs = [{"is_negative": True, "refused": True},
          {"is_negative": True, "refused": False},
          {"is_negative": False, "refused": False}]
    assert refusal_stats(rs) == {"n": 2, "refusal_rate": 0.5}

    print("rag_metrics self-test: ALL PASSED")


if __name__ == "__main__":
    _self_test()
