"""
UniDoc-Bench 离线检索评测脚本。

使用示例（从项目根目录）：

    python -m evaluation.run_unidoc_eval \\
        --domain finance \\
        --method baseline_ocr \\
        --top-k 10 \\
        --build-index

结果保存到 data/eval_results/unidoc_{domain}_{method}_{timestamp}.json，包含：
- 每条 query 的逐条指标（Recall@K、RR、AP、首次命中位置、延迟）
- 按 question_type 和 answer_type 的分组统计
- 汇总统计（均值 + 标准差）
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# 加载 backend/.env
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from evaluation.datasets.unidoc_subset import (  # noqa: E402
    DOMAINS,
    UniDocQuerySample,
    get_domain_image_records,
    load_unidoc_domain,
)
from evaluation.metrics import (  # noqa: E402
    RankedList,
    average_precision,
    recall_at_k,
    reciprocal_rank,
)
from evaluation.methods import unidoc_clip, unidoc_ocr, unidoc_proposed  # noqa: E402


def _first_hit_rank(ranked: RankedList) -> int | None:
    for idx, pid in enumerate(ranked.predicted_ids, start=1):
        if pid in ranked.relevant_ids:
            return idx
    return None


def _stats(values: List[float]) -> Dict[str, float]:
    mean = sum(values) / len(values) if values else 0.0
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"mean": round(mean, 4), "std": round(std, 4)}


def _group_stats(records: List[Dict], group_key: str, top_k: int) -> Dict[str, Any]:
    """按指定字段分组统计指标。"""
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for r in records:
        groups[r[group_key]].append(r)

    result = {}
    for group_val, group_records in sorted(groups.items()):
        rr_vals = [r["reciprocal_rank"] for r in group_records]
        r1_vals = [r["recall_at_1"] for r in group_records]
        r5_vals = [r["recall_at_5"] for r in group_records]
        rk_vals = [r[f"recall_at_{top_k}"] for r in group_records]
        ap_vals = [r[f"ap_at_{top_k}"] for r in group_records]
        result[group_val] = {
            "count": len(group_records),
            "recall_at_1": _stats(r1_vals),
            "recall_at_5": _stats(r5_vals),
            f"recall_at_{top_k}": _stats(rk_vals),
            "mrr": _stats(rr_vals),
            f"map_at_{top_k}": _stats(ap_vals),
        }
    return result


def run_experiment(
    domain: str,
    samples: List[UniDocQuerySample],
    method: str,
    top_k: int,
    output_dir: Path,
) -> None:
    ranked_list: List[RankedList] = []
    per_query_records: List[Dict[str, Any]] = []

    for i, sample in enumerate(samples):
        t0 = time.perf_counter()

        if method == "proposed":
            predicted_ids = unidoc_proposed.retrieve(sample.query, domain=domain, top_k=top_k)
        elif method == "baseline_clip":
            predicted_ids = unidoc_clip.retrieve(sample.query, domain=domain, top_k=top_k)
        elif method == "baseline_ocr":
            predicted_ids = unidoc_ocr.retrieve(sample.query, domain=domain, top_k=top_k)
        else:
            raise ValueError(f"Unsupported method: {method}")

        latency_ms = (time.perf_counter() - t0) * 1000
        ranked = RankedList(predicted_ids=predicted_ids, relevant_ids=sample.relevant_ids)
        ranked_list.append(ranked)

        fhr = _first_hit_rank(ranked)
        hit_flags = [pid in sample.relevant_ids for pid in predicted_ids]

        per_query_records.append({
            "query_index": i,
            "query": sample.query,
            "domain": sample.domain,
            "question_type": sample.question_type,
            "answer_type": sample.answer_type,
            "relevant_ids": list(sample.relevant_ids),
            "predicted_ids": predicted_ids,
            "hit_flags": hit_flags,
            "hit_count": sum(hit_flags),
            "first_hit_rank": fhr,
            "recall_at_1": recall_at_k(ranked, 1),
            "recall_at_5": recall_at_k(ranked, 5),
            f"recall_at_{top_k}": recall_at_k(ranked, top_k),
            "reciprocal_rank": reciprocal_rank(ranked),
            f"ap_at_{top_k}": average_precision(ranked, top_k),
            "latency_ms": round(latency_ms, 2),
        })

        print(f"  [{i+1}/{len(samples)}] RR={reciprocal_rank(ranked):.2f}  "
              f"first_hit={fhr}  latency={latency_ms:.0f}ms  query={sample.query[:60]}")

    # 汇总统计
    latencies = [r["latency_ms"] for r in per_query_records]
    summary = {
        "method": method,
        "domain": domain,
        "top_k": top_k,
        "num_queries": len(ranked_list),
        "recall_at_1": _stats([recall_at_k(r, 1) for r in ranked_list]),
        "recall_at_5": _stats([recall_at_k(r, 5) for r in ranked_list]),
        f"recall_at_{top_k}": _stats([recall_at_k(r, top_k) for r in ranked_list]),
        "mrr": _stats([reciprocal_rank(r) for r in ranked_list]),
        f"map_at_{top_k}": _stats([average_precision(r, top_k) for r in ranked_list]),
        "latency_ms": _stats(latencies),
        "latency_ms_median": round(statistics.median(latencies), 2),
    }

    # 分组统计
    by_question_type = _group_stats(per_query_records, "question_type", top_k)
    by_answer_type = _group_stats(per_query_records, "answer_type", top_k)

    # 打印汇总
    print(f"\n{'='*55}")
    print(f"Method: {method}  |  Domain: {domain}  |  Queries: {summary['num_queries']}  |  Top-K: {top_k}")
    print(f"{'='*55}")
    for k in (1, 5, top_k):
        key = f"recall_at_{k}"
        s = summary[key]
        print(f"Recall@{k}:   {s['mean']:.4f}  (±{s['std']:.4f})")
    print(f"MRR:         {summary['mrr']['mean']:.4f}  (±{summary['mrr']['std']:.4f})")
    print(f"mAP@{top_k}:     {summary[f'map_at_{top_k}']['mean']:.4f}  (±{summary[f'map_at_{top_k}']['std']:.4f})")
    print(f"Latency(ms): mean={summary['latency_ms']['mean']:.1f}  "
          f"median={summary['latency_ms_median']:.1f}  std={summary['latency_ms']['std']:.1f}")

    print(f"\n--- By question_type ---")
    for qt, s in by_question_type.items():
        print(f"  {qt} (n={s['count']}): Recall@{top_k}={s[f'recall_at_{top_k}']['mean']:.4f}  MRR={s['mrr']['mean']:.4f}")

    print(f"\n--- By answer_type ---")
    for at, s in by_answer_type.items():
        print(f"  {at} (n={s['count']}): Recall@{top_k}={s[f'recall_at_{top_k}']['mean']:.4f}  MRR={s['mrr']['mean']:.4f}")

    # 保存结果
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"unidoc_{domain}_{method}_{timestamp}.json"

    result = {
        "summary": summary,
        "by_question_type": by_question_type,
        "by_answer_type": by_answer_type,
        "per_query": per_query_records,
        "meta": {
            "timestamp": timestamp,
            "method": method,
            "domain": domain,
            "top_k": top_k,
        },
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存到: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline retrieval evaluation on UniDoc-Bench subset.")
    parser.add_argument("--domain", type=str, required=True, choices=DOMAINS, help="Domain to evaluate.")
    parser.add_argument(
        "--method",
        type=str,
        choices=["proposed", "baseline_clip", "baseline_ocr"],
        default="baseline_ocr",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--build-index", action="store_true", help="Build index before evaluating.")
    parser.add_argument("--subset-root", type=str, default="data/UniDoc-Bench-subset")
    parser.add_argument("--output-dir", type=str, default="data/eval_results")
    args = parser.parse_args()

    subset_root = Path(args.subset_root)
    output_dir = Path(args.output_dir)

    print(f"Loading domain '{args.domain}' from {subset_root}...")
    samples = load_unidoc_domain(args.domain, subset_root)
    print(f"Loaded {len(samples)} queries.")

    if args.build_index:
        print(f"Building index for method '{args.method}'...")
        image_records = get_domain_image_records(args.domain, subset_root)
        print(f"Candidate images: {len(image_records)}")

        if args.method == "proposed":
            unidoc_proposed.build_index(args.domain, image_records)
        elif args.method == "baseline_clip":
            unidoc_clip.build_index(args.domain, image_records)
        elif args.method == "baseline_ocr":
            unidoc_ocr.build_index(args.domain, image_records)
    else:
        # 检查索引是否存在
        if args.method == "proposed":
            has_index = unidoc_proposed.check_index(args.domain)
        elif args.method == "baseline_clip":
            has_index = unidoc_clip.check_index(args.domain)
        else:
            has_index = unidoc_ocr.check_index(args.domain)

        if not has_index:
            print(f"[ERROR] Index for '{args.method}' domain '{args.domain}' is empty. "
                  "Run with --build-index first.")
            return

    print(f"\nRunning evaluation: method={args.method}  domain={args.domain}  top_k={args.top_k}")
    run_experiment(
        domain=args.domain,
        samples=samples,
        method=args.method,
        top_k=args.top_k,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    main()
