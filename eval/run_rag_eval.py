"""RAG 测评：检索层指标 + 消融实验 + 生成层（Keypoint Coverage / LLM-as-Judge）。

用法：
    python eval/run_rag_eval.py [--limit N] [--skip-generation] [--skip-judge] [--out-dir eval/reports]

说明：
- 检索基线使用系统真实管线 rag.retriever.retrieve(q, top_k=5)，按 k=1/3/5 切片。
- 消融 no_rewrite：绕过查询改写，直接用原始问题单路检索（chroma_query n_results=5）。
- 生成层复刻 ConsultationAgent.process 的调用路径（retrieve→chat），仅将流式输出替换为
  非流式（同模型同提示词同温度），以便捕获答案文本。
- LLM-as-Judge 使用与生成相同的 LLM 接口（utils.llm_client.chat）。
"""
import argparse
import contextlib
import csv
import io
import json
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from eval.utils import load_dataset, patch_requests_ssl  # noqa: E402
from eval.metrics import rag_metrics as RM  # noqa: E402
from rag.retriever import retrieve  # noqa: E402
from rag.vector_store import query as chroma_query  # noqa: E402
from agents.consultation_agent import ConsultationAgent  # noqa: E402

KS = [1, 3, 5]
MAX_RETRY = 3

JUDGE_SYSTEM_PROMPT = """你是一名严格的医疗问答评测员。请根据问题、参考文档和候选回答进行评分。

评分标准：
- faithfulness（忠实度，1-5）：回答中的医疗事实断言是否都能被参考文档支持。
  出现文档中不存在的事实（编造）→ 低分。
  若候选回答明确表示无法回答、信息不足，faithfulness 记 5。
- relevance（相关性，1-5）：回答是否直接回应问题、切题且不冗余。
- refused（布尔）：回答是否明确表示无法回答、信息不足、超出能力范围或仅建议就医。
- rationale：简要说明打分依据（50字以内）。

严格以 JSON 输出，不要输出任何其他内容：
{"faithfulness": 1-5, "relevance": 1-5, "refused": true/false, "rationale": "..."}"""


def call_with_retry(fn, max_retry: int = MAX_RETRY):
    """带重试的调用：网络抖动或 LLM 失败串时退避重试。"""
    last_err = None
    for attempt in range(max_retry):
        try:
            result = fn()
            if isinstance(result, str) and "[LLM调用失败]" in result:
                raise RuntimeError("LLM调用失败")
            return result
        except Exception as e:
            last_err = e
            if attempt < max_retry - 1:
                time.sleep(1 + attempt)
    raise last_err


def generate_answer(question: str) -> tuple[str, str]:
    """复刻 ConsultationAgent.process：retrieve → chat（流式替换为非流式）。"""
    rag_result = call_with_retry(lambda: retrieve(question))
    context = rag_result.get("context", "")
    agent = ConsultationAgent()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        if context:
            answer = agent.chat(question, extra_context=context, temperature=0.7)
        else:
            answer = agent.chat(question, temperature=0.7)
    return answer, context


def llm_judge(question: str, context: str, answer: str) -> dict:
    """LLM-as-Judge：忠实度 / 相关性 / 拒答判定。"""
    from utils.llm_client import chat  # 延迟导入，避免评测前的副作用

    user_prompt = (
        f"【问题】\n{question}\n\n"
        f"【参考文档】\n{context or '(空，无检索结果)'}\n\n"
        f"【候选回答】\n{answer}\n\n"
        "请按 JSON 格式输出评分。"
    )
    response = call_with_retry(
        lambda: chat([
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ], temperature=0.2)
    )
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(response[start:end])
            return {
                "faithfulness": float(result.get("faithfulness", 0)),
                "relevance": float(result.get("relevance", 0)),
                "refused": bool(result.get("refused", False)),
                "rationale": result.get("rationale", ""),
            }
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return {"faithfulness": 0.0, "relevance": 0.0, "refused": False, "rationale": "judge_parse_fail"}


def retrieval_run(sample: dict) -> dict:
    """单样本检索：基线（真实管线 top_k=5）+ no_rewrite 消融。"""
    question = sample["question"]

    t0 = time.time()
    full = call_with_retry(lambda: retrieve(question, top_k=5))
    full_time = time.time() - t0
    full_ids = [r["id"] for r in full["results"]]

    t0 = time.time()
    raw = call_with_retry(lambda: chroma_query(question, n_results=5))
    raw_time = time.time() - t0
    raw_ids = [r["id"] for r in raw]

    return {
        "baseline_ids": full_ids,
        "baseline_time": round(full_time, 2),
        "rewritten_query": full.get("rewritten_query"),
        "keywords": full.get("keywords"),
        "no_rewrite_ids": raw_ids,
        "no_rewrite_time": round(raw_time, 2),
    }


def run(dataset_path: str, out_dir: str, limit: int = None,
        skip_generation: bool = False, skip_judge: bool = False):
    os.makedirs(out_dir, exist_ok=True)
    samples = load_dataset(dataset_path)
    if limit:
        samples = samples[:limit]

    positive = [s for s in samples if s["gold_chunk_ids"]]
    negative = [s for s in samples if not s["gold_chunk_ids"]]
    print(f"正样本 {len(positive)} 条，负样本 {len(negative)} 条")

    # ---- 检索层 ----
    results = []
    for i, sample in enumerate(positive, 1):
        rec = retrieval_run(sample)
        results.append({**sample, **rec})
        if i % 10 == 0 or i == len(positive):
            print(f"  [检索 {i}/{len(positive)}]", flush=True)

    # ---- 生成层（可选） ----
    if not skip_generation:
        for i, r in enumerate(results, 1):
            t0 = time.time()
            answer, context = generate_answer(r["question"])
            r["answer"] = answer
            r["gen_time"] = round(time.time() - t0, 2)
            r["context_used"] = context
            if i % 10 == 0 or i == len(results):
                print(f"  [生成 {i}/{len(results)}]", flush=True)

    if not skip_generation and not skip_judge:
        for i, r in enumerate(results, 1):
            r["judge"] = llm_judge(r["question"], r.get("context_used", ""), r["answer"])
            if i % 10 == 0 or i == len(results):
                print(f"  [评分 {i}/{len(results)}]", flush=True)

    # 负样本：生成 + 拒答评测
    if not skip_generation:
        neg_results = []
        for i, sample in enumerate(negative, 1):
            answer, context = generate_answer(sample["question"])
            rec = {**sample, "answer": answer, "context_used": context}
            if not skip_judge:
                rec["judge"] = llm_judge(sample["question"], context, answer)
            neg_results.append(rec)
            if i % 5 == 0 or i == len(negative):
                print(f"  [负样本 {i}/{len(negative)}]", flush=True)
    else:
        neg_results = []

    # ---- 指标计算 ----
    summary = {
        "dataset": os.path.basename(dataset_path),
        "n_positive": len(positive),
        "n_negative": len(negative),
    }

    golds = [r["gold_chunk_ids"] for r in results]

    summary["retrieval"] = {}
    for mode, key in (("baseline", "baseline_ids"), ("no_rewrite", "no_rewrite_ids")):
        preds = [r[key] for r in results]
        summary["retrieval"][mode] = RM.summarize_retrieval(preds, golds, KS)
        # 按题型拆分
        by_type = {}
        for qt in ("factoid", "paraphrase", "colloquial", "multi-hop", "adversarial"):
            idxs = [i for i, r in enumerate(results) if r["question_type"] == qt]
            if not idxs:
                continue
            by_type[qt] = RM.summarize_retrieval(
                [preds[i] for i in idxs], [golds[i] for i in idxs], [3])
        summary["retrieval"][mode]["by_type"] = by_type

    # 消融对比：改写带来的增益
    b3 = summary["retrieval"]["baseline"]["recall@3"]
    n3 = summary["retrieval"]["no_rewrite"]["recall@3"]
    summary["rewrite_ablation"] = {
        "baseline_recall@3": b3,
        "no_rewrite_recall@3": n3,
        "delta_recall@3": round(b3 - n3, 4),
    }

    # ---- 生成层指标 ----
    if not skip_generation:
        kp_cov = [RM.keypoint_coverage(r["answer"], r["gold_keypoints"]) for r in results]
        summary["generation"] = {
            "keypoint_coverage": sum(kp_cov) / len(kp_cov) if kp_cov else 0.0,
            "n_answered": len(results),
        }
        if not skip_judge:
            faith = [r["judge"]["faithfulness"] for r in results]
            rel = [r["judge"]["relevance"] for r in results]
            summary["generation"]["faithfulness_mean"] = sum(faith) / len(faith)
            summary["generation"]["relevance_mean"] = sum(rel) / len(rel)
            summary["generation"]["faithfulness_le2_ratio"] = (
                sum(1 for f in faith if f <= 2) / len(faith))
            # 检索质量与忠实度相关性（粗看）：按 recall@3 分组
            for bucket_name, cond in (
                ("hit", lambda i: bool(set(results[i]["gold_chunk_ids"]) & set(results[i]["baseline_ids"][:3]))),
                ("miss", lambda i: not (set(results[i]["gold_chunk_ids"]) & set(results[i]["baseline_ids"][:3]))),
            ):
                idxs = [i for i in range(len(results)) if cond(i)]
                if idxs:
                    summary["generation"][f"faithfulness_by_recall3_{bucket_name}"] = (
                        sum(results[i]["judge"]["faithfulness"] for i in idxs) / len(idxs))

        if neg_results:
            neg_refused = [bool(n["judge"]["refused"]) for n in neg_results] if not skip_judge else []
            summary["negative"] = {
                "n": len(neg_results),
                "refusal_rate": sum(neg_refused) / len(neg_refused) if neg_refused else None,
                "keypoint_na": None,
            }
            if not skip_judge:
                neg_faith = [n["judge"]["faithfulness"] for n in neg_results]
                summary["negative"]["faithfulness_mean"] = sum(neg_faith) / len(neg_faith)
                summary["negative"]["fabricated"] = [
                    {"id": n["id"], "question": n["question"],
                     "judge": n["judge"]}
                    for n in neg_results if n["judge"]["faithfulness"] <= 2
                ]

    # ---- 保存 ----
    results_path = os.path.join(out_dir, "rag_results.jsonl")
    with open(results_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if neg_results:
        with open(os.path.join(out_dir, "rag_negative_results.jsonl"), "w", encoding="utf-8") as f:
            for r in neg_results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary_path = os.path.join(out_dir, "rag_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 错误样本：recall@3=0 或 忠实度低
    errors_path = os.path.join(out_dir, "rag_errors.csv")
    with open(errors_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "question", "question_type", "gold_chunk_ids",
                         "baseline_top3", "no_rewrite_top3", "keypoint_coverage",
                         "faithfulness", "relevance", "rationale"])
        for i, r in enumerate(results):
            hit = bool(set(r["gold_chunk_ids"]) & set(r["baseline_ids"][:3]))
            judge = r.get("judge", {})
            faith = judge.get("faithfulness", "")
            if not hit or (isinstance(faith, (int, float)) and faith <= 2):
                writer.writerow([
                    r["id"], r["question"], r["question_type"],
                    ";".join(r["gold_chunk_ids"]), ";".join(r["baseline_ids"][:3]),
                    ";".join(r["no_rewrite_ids"][:3]),
                    round(RM.keypoint_coverage(r.get("answer", ""), r["gold_keypoints"]), 3),
                    faith, judge.get("relevance", ""), judge.get("rationale", ""),
                ])

    print(f"\n结果已保存：{summary_path} / {results_path} / {errors_path}")
    return summary


def print_summary(s: dict):
    print("\n" + "=" * 64)
    print("RAG 检索测评结果（recall@k / hit@k / MRR）")
    print("=" * 64)
    for mode in ("baseline", "no_rewrite"):
        m = s["retrieval"][mode]
        print(f"\n[{mode}]")
        for k in KS:
            print(f"  k={k}: recall={m[f'recall@{k}']:.4f}  "
                  f"precision={m[f'precision@{k}']:.4f}  hit={m[f'hit@{k}']:.4f}")
        print(f"  MRR={m['mrr']:.4f}  nDCG@3={m['ndcg@3']:.4f}")
        print("  题型 recall@3:")
        for qt, tm in m["by_type"].items():
            print(f"    {qt:<12} recall@3={tm['recall@3']:.4f}  hit@3={tm['hit@3']:.4f}")
    print(f"\n改写消融: 基线 recall@3={s['rewrite_ablation']['baseline_recall@3']:.4f}  "
          f"无改写={s['rewrite_ablation']['no_rewrite_recall@3']:.4f}  "
          f"Δ={s['rewrite_ablation']['delta_recall@3']:+.4f}")
    if "generation" in s:
        g = s["generation"]
        print("\n生成层:")
        print(f"  Keypoint Coverage: {g['keypoint_coverage']:.4f}")
        if "faithfulness_mean" in g:
            print(f"  忠实度均值: {g['faithfulness_mean']:.2f}/5  "
                  f"相关性均值: {g['relevance_mean']:.2f}/5  "
                  f"忠实度≤2占比: {g['faithfulness_le2_ratio']:.4f}")
            if "faithfulness_by_recall3_hit" in g:
                print(f"  忠实度(检索命中): {g['faithfulness_by_recall3_hit']:.2f}  "
                      f"忠实度(检索未命中): {g['faithfulness_by_recall3_miss']:.2f}")
    if "negative" in s and s["negative"].get("refusal_rate") is not None:
        n = s["negative"]
        print(f"\n负样本: n={n['n']}  拒答率={n['refusal_rate']:.4f}  "
              f"忠实度均值={n['faithfulness_mean']:.2f}/5  "
              f"疑似编造={len(n['fabricated'])}条")


if __name__ == "__main__":
    patch_requests_ssl()
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="仅评测前 N 条（调试用）")
    parser.add_argument("--skip-generation", action="store_true", help="跳过生成与评分")
    parser.add_argument("--skip-judge", action="store_true", help="跳过 LLM-as-Judge")
    parser.add_argument("--out-dir", default=os.path.join(PROJECT_ROOT, "eval", "reports"))
    args = parser.parse_args()

    dataset = os.path.join(PROJECT_ROOT, "eval", "datasets", "rag_test.jsonl")
    summary = run(dataset, args.out_dir, args.limit, args.skip_generation, args.skip_judge)
    print_summary(summary)
