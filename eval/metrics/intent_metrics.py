"""意图分类指标：accuracy / per-class P·R·F1 / macro-F1 / 混淆矩阵 / 槽位F1 / 置信度校准。

不依赖 sklearn，全部手写实现。
"""
from collections import Counter, defaultdict


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return 0.0
    return sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)


def per_class_metrics(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    """每类 P/R/F1 与支持数。"""
    result = {}
    for label in labels:
        tp = sum(t == label and p == label for t, p in zip(y_true, y_pred))
        fp = sum(t != label and p == label for t, p in zip(y_true, y_pred))
        fn = sum(t == label and p != label for t, p in zip(y_true, y_pred))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        result[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": tp + fn,
        }
    return result


def macro_f1(y_true: list[str], y_pred: list[str], labels: list[str]) -> float:
    metrics = per_class_metrics(y_true, y_pred, labels)
    return sum(m["f1"] for m in metrics.values()) / len(labels)


def weighted_f1(y_true: list[str], y_pred: list[str], labels: list[str]) -> float:
    metrics = per_class_metrics(y_true, y_pred, labels)
    total = len(y_true)
    return sum(m["f1"] * m["support"] for m in metrics.values()) / total if total else 0.0


def confusion_matrix(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    """返回 {true_label: {pred_label: count}}。"""
    matrix = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(y_true, y_pred):
        matrix[t][p] += 1
    return matrix


def _normalize_slot_value(v) -> str:
    """槽位值规范化：去空白、小写、去标点。"""
    return "".join(ch for ch in str(v).strip().lower() if ch.isalnum())


def _flatten_slot_values(slots: dict) -> dict:
    """把 {field: value|list} 规范化为 {field: set(归一化值)}。"""
    flat = {}
    for field, value in (slots or {}).items():
        field = field.strip().lower()
        if isinstance(value, (list, tuple)):
            values = value
        else:
            values = [value]
        flat[field] = {_normalize_slot_value(v) for v in values if v}
    return flat


def slot_f1(gold_slots_list: list[dict], pred_slots_list: list[dict]) -> dict:
    """槽位提取 F1（字段级，值取集合交并）。

    Returns:
        {"per_field": {field: {"precision":…,"recall":…,"f1":…}}, "macro_f1": float}
    """
    all_fields = sorted(set().union(
        *[_flatten_slot_values(s).keys() for s in gold_slots_list],
        *[_flatten_slot_values(s).keys() for s in pred_slots_list],
    ))
    per_field = {}
    for field in all_fields:
        tp = fp = fn = 0
        for gold, pred in zip(gold_slots_list, pred_slots_list):
            g = _flatten_slot_values(gold).get(field, set())
            p = _flatten_slot_values(pred).get(field, set())
            tp += len(g & p)
            fp += len(p - g)
            fn += len(g - p)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_field[field] = {"precision": precision, "recall": recall, "f1": f1}
    macro = sum(v["f1"] for v in per_field.values()) / len(per_field) if per_field else 0.0
    return {"per_field": per_field, "macro_f1": macro}


def clarification_stats(samples: list[dict], gold_intent_key: str = "gold_intent",
                        pred_intent_key: str = "pred_intent",
                        pred_clarify_key: str = "pred_needs_clarification") -> dict:
    """澄清行为统计（仅统计带 gold_clarification 标注的样本）。

    返回 {"rate": 模型触发澄清的比例, "precision": 触发澄清中真正该澄清的比例,
          "recall": 该澄清样本中被触发澄清的比例, "n": 参与统计的样本数}
    """
    subset = [s for s in samples if "gold_clarification" in s]
    if not subset:
        return {"rate": 0.0, "precision": None, "recall": None, "n": 0}
    triggered = sum(bool(s.get(pred_clarify_key)) for s in subset)
    tp = sum(bool(s.get(pred_clarify_key)) and bool(s["gold_clarification"]) for s in subset)
    gold_pos = sum(bool(s["gold_clarification"]) for s in subset)
    return {
        "rate": triggered / len(subset),
        "precision": tp / triggered if triggered else 0.0,
        "recall": tp / gold_pos if gold_pos else 0.0,
        "n": len(subset),
    }


def calibration_stats(y_true: list[str], y_pred: list[str], confidences: list[float]) -> dict:
    """置信度校准：按桶统计样本数与准确率。

    桶：<0.6, 0.6-0.7, 0.7-0.8, 0.8-0.9, 0.9-1.0
    """
    buckets = [(0.0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    result = []
    for lo, hi in buckets:
        idxs = [i for i, c in enumerate(confidences) if lo <= c < hi]
        if not idxs:
            continue
        correct = sum(y_true[i] == y_pred[i] for i in idxs)
        result.append({
            "bucket": f"[{lo},{hi})" if hi <= 1.0 else "[0.9,1.0]",
            "count": len(idxs),
            "accuracy": correct / len(idxs),
        })
    return result


def summarize(y_true: list[str], y_pred: list[str], confidences: list[float],
              labels: list[str]) -> dict:
    """汇总所有指标。"""
    return {
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(y_true, y_pred, labels),
        "weighted_f1": weighted_f1(y_true, y_pred, labels),
        "per_class": per_class_metrics(y_true, y_pred, labels),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels),
        "calibration": calibration_stats(y_true, y_pred, confidences),
    }


def _self_test():
    """手工计算的自测用例。"""
    y_true = ["a", "a", "b", "b", "c"]
    y_pred = ["a", "b", "b", "b", "c"]
    labels = ["a", "b", "c"]

    assert abs(accuracy(y_true, y_pred) - 0.8) < 1e-9
    pc = per_class_metrics(y_true, y_pred, labels)
    # a: tp=1 fp=0 fn=1 → P=1 R=0.5 F1=2/3; b: tp=2 fp=1 fn=0 → P=2/3 R=1 F1=0.8; c: 1/1/1
    assert abs(pc["a"]["f1"] - 2 / 3) < 1e-9
    assert abs(pc["b"]["precision"] - 2 / 3) < 1e-9
    assert abs(pc["c"]["f1"] - 1.0) < 1e-9
    assert abs(macro_f1(y_true, y_pred, labels) - (2 / 3 + 0.8 + 1.0) / 3) < 1e-9
    cm = confusion_matrix(y_true, y_pred, labels)
    assert cm["a"]["b"] == 1 and cm["b"]["b"] == 2 and cm["c"]["c"] == 1

    slot = slot_f1(
        [{"symptoms": ["头痛", "头晕"]}, {"symptoms": ["咳嗽"], "department": "呼吸内科"}],
        [{"symptoms": ["头疼", "头晕"]}, {"symptoms": ["咳嗽"]}],
    )
    # symptoms: tp=2(头晕,咳嗽) fp=1(头疼) fn=1(头痛) → P=2/3 R=2/3
    assert abs(slot["per_field"]["symptoms"]["f1"] - 2 / 3) < 1e-9
    # department: tp=0 fp=0 fn=1 → R=0
    assert slot["per_field"]["department"]["recall"] == 0.0

    calib = calibration_stats(["a", "a"], ["a", "b"], [0.5, 0.95])
    assert calib[0] == {"bucket": "[0.0,0.6)", "count": 1, "accuracy": 1.0}
    assert calib[1]["bucket"] == "[0.9,1.0]" and calib[1]["accuracy"] == 0.0

    clar = clarification_stats([
        {"gold_clarification": True, "pred_needs_clarification": True},
        {"gold_clarification": False, "pred_needs_clarification": True},
        {"gold_clarification": True, "pred_needs_clarification": False},
    ])
    assert clar["rate"] == 2 / 3 and clar["precision"] == 0.5 and clar["recall"] == 0.5

    print("intent_metrics self-test: ALL PASSED")


if __name__ == "__main__":
    _self_test()
