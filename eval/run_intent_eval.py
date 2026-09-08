"""意图分类测评：遍历 eval/datasets/intent_test.jsonl，调用 RouterAgent.classify_intent，
输出指标汇总（JSON）、逐条结果（JSONL）与错误样本（CSV）。

用法：
    python eval/run_intent_eval.py [--limit N] [--out-dir eval/reports]
"""
import argparse
import csv
import json
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from eval.utils import load_dataset, patch_requests_ssl  # noqa: E402
from eval.metrics import intent_metrics as M  # noqa: E402
from agents.router_agent import RouterAgent  # noqa: E402

LABELS = ["appointment", "queue", "consultation", "diagnosis", "chitchat"]
MAX_RETRY = 3


def classify_with_retry(router: RouterAgent, text: str) -> dict:
    """调用分类并重试 LLM 失败。每次调用前重置历史保证样本独立。"""
    for attempt in range(MAX_RETRY):
        router.reset()  # 保证每条样本独立，不受历史影响
        result = router.classify_intent(text)
        # llm_client 失败时响应含 "[LLM调用失败]"，此时 classify_intent 走 JSON 解析失败兜底，
        # 特征为 confidence=0.3 且意图为 chitchat；用重试兜住网络抖动
        if result.get("confidence") == 0.3 and result.get("intent") == "chitchat":
            if attempt < MAX_RETRY - 1:
                time.sleep(1 + attempt)
                continue
        return result
    return result


def is_correct(sample: dict, pred: dict) -> bool:
    """判定正确性：标注了 gold_clarification 的歧义样本，模型触发澄清也算对。"""
    if sample.get("gold_clarification") and pred.get("needs_clarification"):
        return True
    return pred.get("intent") == sample["gold_intent"]


def run(dataset_path: str, out_dir: str, limit: int = None):
    os.makedirs(out_dir, exist_ok=True)
    samples = load_dataset(dataset_path)
    if limit:
        samples = samples[:limit]

    router = RouterAgent()
    results = []
    for i, sample in enumerate(samples, 1):
        pred = classify_with_retry(router, sample["text"])
        pred_intent = pred.get("intent", "chitchat")
        results.append({
            "id": sample["id"],
            "text": sample["text"],
            "gold_intent": sample["gold_intent"],
            "gold_slots": sample.get("gold_slots", {}),
            "gold_clarification": sample.get("gold_clarification", False),
            "difficulty": sample.get("difficulty"),
            "edge_case_type": sample.get("edge_case_type"),
            "pred_intent": pred_intent,
            "pred_confidence": pred.get("confidence", 0.0),
            "pred_needs_clarification": pred.get("needs_clarification", False),
            "pred_clarification_question": pred.get("clarification_question"),
            "pred_extracted_info": pred.get("extracted_info", {}),
            "correct": is_correct(sample, pred),
        })
        if i % 20 == 0 or i == len(samples):
            print(f"  [{i}/{len(samples)}] processed", flush=True)

    # 保存逐条结果
    results_path = os.path.join(out_dir, "intent_results.jsonl")
    with open(results_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---- 汇总指标 ----
    y_true = [r["gold_intent"] for r in results]
    y_pred = [r["pred_intent"] for r in results]
    confs = [r["pred_confidence"] for r in results]

    summary = {
        "dataset": os.path.basename(dataset_path),
        "n": len(results),
        "strict_accuracy": M.accuracy(y_true, y_pred),
        "macro_f1": M.macro_f1(y_true, y_pred, LABELS),
        "weighted_f1": M.weighted_f1(y_true, y_pred, LABELS),
        "per_class": M.per_class_metrics(y_true, y_pred, LABELS),
        "confusion_matrix": M.confusion_matrix(y_true, y_pred, LABELS),
        "calibration": M.calibration_stats(y_true, y_pred, confs),
    }

    # 带澄清豁免的正确率（对 gold_clarification 样本）
    summary["accuracy_with_clarification"] = (
        sum(r["correct"] for r in results) / len(results) if results else 0.0
    )

    # 难度分层准确率
    summary["by_difficulty"] = {}
    for diff in ("easy", "medium", "hard", "adversarial"):
        sub = [r for r in results if r["difficulty"] == diff]
        if sub:
            summary["by_difficulty"][diff] = {
                "n": len(sub),
                "accuracy": sum(r["correct"] for r in sub) / len(sub),
            }

    # 边界类型准确率（多意图 / 否定 / 隐式关键词 / 域外）
    summary["by_edge_case"] = {}
    for r in results:
        key = r["edge_case_type"] or "none"
        summary["by_edge_case"].setdefault(key, {"n": 0, "correct": 0})
        summary["by_edge_case"][key]["n"] += 1
        summary["by_edge_case"][key]["correct"] += int(r["correct"])
    for key, v in summary["by_edge_case"].items():
        v["accuracy"] = v["correct"] / v["n"]
        del v["correct"]

    # 槽位提取 F1（仅统计带 gold_slots 的样本）
    slot_samples = [r for r in results if r["gold_slots"]]
    summary["slot_f1"] = M.slot_f1(
        [r["gold_slots"] for r in slot_samples],
        [r["pred_extracted_info"] for r in slot_samples],
    )
    summary["slot_f1"]["n"] = len(slot_samples)

    # 澄清行为统计
    summary["clarification"] = M.clarification_stats(results)

    # 典型混淆对
    confusion_pairs = {}
    for r in results:
        if r["pred_intent"] != r["gold_intent"]:
            pair = f"{r['gold_intent']}→{r['pred_intent']}"
            confusion_pairs[pair] = confusion_pairs.get(pair, 0) + 1
    summary["top_confusion_pairs"] = sorted(
        confusion_pairs.items(), key=lambda x: -x[1])[:8]

    summary_path = os.path.join(out_dir, "intent_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 错误样本 CSV
    errors = [r for r in results if not r["correct"]]
    errors_path = os.path.join(out_dir, "intent_errors.csv")
    with open(errors_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text", "gold_intent", "pred_intent", "confidence",
                         "difficulty", "edge_case_type", "needs_clarification",
                         "clarification_question", "pred_extracted_info"])
        for r in errors:
            writer.writerow([r["id"], r["text"], r["gold_intent"], r["pred_intent"],
                             r["pred_confidence"], r["difficulty"], r["edge_case_type"],
                             r["pred_needs_clarification"], r["pred_clarification_question"],
                             json.dumps(r["pred_extracted_info"], ensure_ascii=False)])

    print(f"\n结果已保存：{summary_path} / {results_path} / {errors_path}")
    return summary


def print_summary(s: dict):
    print("\n" + "=" * 64)
    print("意图分类测评结果")
    print("=" * 64)
    print(f"样本数: {s['n']}    严格 Accuracy: {s['strict_accuracy']:.4f}    "
          f"Macro-F1: {s['macro_f1']:.4f}")
    print(f"澄清豁免 Accuracy: {s['accuracy_with_clarification']:.4f}")
    print("\n每类指标:")
    print(f"{'类别':<14}{'P':>8}{'R':>8}{'F1':>8}{'N':>6}")
    for label, m in s["per_class"].items():
        print(f"{label:<14}{m['precision']:>8.4f}{m['recall']:>8.4f}{m['f1']:>8.4f}{m['support']:>6}")
    print("\n难度分层准确率:")
    for diff, v in s["by_difficulty"].items():
        print(f"  {diff:<12} n={v['n']:<3} acc={v['accuracy']:.4f}")
    print("\n主要混淆对:")
    for pair, count in s["top_confusion_pairs"]:
        print(f"  {pair}: {count}")
    print("\n置信度校准:")
    for b in s["calibration"]:
        print(f"  {b['bucket']:<10} n={b['count']:<3} acc={b['accuracy']:.4f}")


if __name__ == "__main__":
    patch_requests_ssl()
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="仅评测前 N 条（调试用）")
    parser.add_argument("--out-dir", default=os.path.join(PROJECT_ROOT, "eval", "reports"))
    args = parser.parse_args()

    dataset = os.path.join(PROJECT_ROOT, "eval", "datasets", "intent_test.jsonl")
    summary = run(dataset, args.out_dir, args.limit)
    print_summary(summary)
