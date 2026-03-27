"""
UniDoc-Bench-subset 跨领域混合候选池检索评测脚本。

将所有 8 个领域的图片合并为一个大候选池，每条 query 在混合池中检索。
复用已有的 MLLM 描述缓存，减少 API 消耗。

使用示例（从项目根目录）：

    python -m evaluation.run_unidoc_full_eval \\
        --method proposed \\
        --top-k 10 \\
        --build-index

结果保存到 data/eval_results/unidoc_crossdomain_{method}_{timestamp}.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
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
    get_all_image_records,
    load_unidoc_domain,
)
from evaluation.metrics import (  # noqa: E402
    RankedList,
    average_precision,
    recall_at_k,
    reciprocal_rank,
)
from evaluation.methods import unidoc_clip, unidoc_ocr, unidoc_proposed  # noqa: E402

# 跨领域实验使用一个虚拟 domain key，用于索引命名
CROSSDOMAIN_KEY = "crossdomain"
DEFAULT_REUSE_CACHE_DATASETS = ["UniDoc-Bench-subset"]


def _configure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_stdio()


def _safe_console_text(text: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _print_safe(*parts: object, sep: str = " ", end: str = "\n") -> None:
    message = sep.join(str(part) for part in parts)
    print(_safe_console_text(message), end=end)


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
            predicted_ids = unidoc_proposed.retrieve(sample.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
        elif method == "baseline_clip":
            predicted_ids = unidoc_clip.retrieve(sample.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
        elif method == "baseline_ocr":
            predicted_ids = unidoc_ocr.retrieve(sample.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
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

        _print_safe(
            f"  [{i+1}/{len(samples)}] RR={reciprocal_rank(ranked):.2f}  "
            f"first_hit={fhr}  latency={latency_ms:.0f}ms  "
            f"domain={sample.domain}  query={sample.query[:50]}"
        )

    latencies = [r["latency_ms"] for r in per_query_records]
    summary = {
        "method": method,
        "domain": "all (cross-domain pool)",
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

    by_domain = _group_stats(per_query_records, "domain", top_k)
    by_question_type = _group_stats(per_query_records, "question_type", top_k)
    by_answer_type = _group_stats(per_query_records, "answer_type", top_k)

    _print_safe(f"\n{'='*60}")
    _print_safe(f"Method: {method}  |  Pool: cross-domain  |  Queries: {summary['num_queries']}  |  Top-K: {top_k}")
    _print_safe(f"{'='*60}")
    for k in (1, 5, top_k):
        key = f"recall_at_{k}"
        s = summary[key]
        _print_safe(f"Recall@{k}:   {s['mean']:.4f}  (\u00b1{s['std']:.4f})")
    _print_safe(f"MRR:         {summary['mrr']['mean']:.4f}  (\u00b1{summary['mrr']['std']:.4f})")
    _print_safe(f"mAP@{top_k}:     {summary[f'map_at_{top_k}']['mean']:.4f}  (\u00b1{summary[f'map_at_{top_k}']['std']:.4f})")
    _print_safe(
        f"Latency(ms): mean={summary['latency_ms']['mean']:.1f}  "
        f"median={summary['latency_ms_median']:.1f}  std={summary['latency_ms']['std']:.1f}"
    )

    _print_safe(f"\n--- By domain ---")
    for d, s in by_domain.items():
        _print_safe(f"  {d} (n={s['count']}): Recall@{top_k}={s[f'recall_at_{top_k}']['mean']:.4f}  MRR={s['mrr']['mean']:.4f}")

    _print_safe(f"\n--- By question_type ---")
    for qt, s in by_question_type.items():
        _print_safe(f"  {qt} (n={s['count']}): Recall@{top_k}={s[f'recall_at_{top_k}']['mean']:.4f}  MRR={s['mrr']['mean']:.4f}")

    _print_safe(f"\n--- By answer_type ---")
    for at, s in by_answer_type.items():
        _print_safe(f"  {at} (n={s['count']}): Recall@{top_k}={s[f'recall_at_{top_k}']['mean']:.4f}  MRR={s['mrr']['mean']:.4f}")

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"unidoc_crossdomain_{method}_{timestamp}.json"

    result = {
        "summary": summary,
        "by_domain": by_domain,
        "by_question_type": by_question_type,
        "by_answer_type": by_answer_type,
        "per_query": per_query_records,
        "meta": {
            "timestamp": timestamp,
            "method": method,
            "domain": "all",
            "top_k": top_k,
            "dataset_name": "UniDoc-Bench-subset",
            "candidate_pool": "cross_domain_all_subset",
        },
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_safe(f"\n结果已保存到: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline retrieval evaluation on cross-domain merged pool from UniDoc-Bench-subset."
    )
    parser.add_argument(
        "--method",
        type=str,
        choices=["proposed", "baseline_clip", "baseline_ocr"],
        default="proposed",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--build-index", action="store_true", help="Build index before evaluating.")
    parser.add_argument("--dataset-root", type=str, default="data/UniDoc-Bench-subset")
    parser.add_argument("--output-dir", type=str, default="data/eval_results")
    parser.add_argument("--dataset-name", type=str, default="UniDoc-Bench-crossdomain")
    parser.add_argument("--cache-dir", type=str, default="data/cache/unidoc_proposed")
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reuse successful proposed cache records (default: enabled).",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry failed proposed cache records instead of skipping them.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore proposed cache and regenerate all descriptions.",
    )
    parser.add_argument(
        "--reuse-cache-dataset",
        action="append",
        default=None,
        help="Additional proposed cache dataset_name to reuse, can be passed multiple times.",
    )
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root)
    output_dir = Path(args.output_dir)
    reuse_cache_datasets = args.reuse_cache_dataset or DEFAULT_REUSE_CACHE_DATASETS

    # 加载全部领域 query
    all_samples: List[UniDocQuerySample] = []
    for domain in DOMAINS:
        try:
            domain_samples = load_unidoc_domain(domain, dataset_root)
            all_samples.extend(domain_samples)
            print(f"  Loaded {len(domain_samples)} queries from domain '{domain}'")
        except FileNotFoundError as e:
            print(f"  [SKIP] {e}")
    print(f"Total queries: {len(all_samples)}")

    if args.build_index:
        print(f"\nBuilding cross-domain merged candidate pool...")
        image_records = get_all_image_records(dataset_root)
        print(f"Total candidate images: {len(image_records)}")

        if args.method == "proposed":
            print(
                "Proposed cache options: "
                f"resume={args.resume}  "
                f"retry_failed={args.retry_failed}  "
                f"force_refresh={args.force_refresh}  "
                f"dataset_name={args.dataset_name}  "
                f"cache_dir={args.cache_dir}  "
                f"reuse_cache_dataset_names={reuse_cache_datasets}"
            )
            unidoc_proposed.build_index(
                CROSSDOMAIN_KEY,
                image_records,
                dataset_name=args.dataset_name,
                cache_dir=args.cache_dir,
                resume=args.resume,
                retry_failed=args.retry_failed,
                force_refresh=args.force_refresh,
                reuse_cache_dataset_names=reuse_cache_datasets,
            )
        elif args.method == "baseline_clip":
            unidoc_clip.build_index(CROSSDOMAIN_KEY, image_records)
        elif args.method == "baseline_ocr":
            unidoc_ocr.build_index(CROSSDOMAIN_KEY, image_records)
    else:
        if args.method == "proposed":
            has_index = unidoc_proposed.check_index(CROSSDOMAIN_KEY)
        elif args.method == "baseline_clip":
            has_index = unidoc_clip.check_index(CROSSDOMAIN_KEY)
        else:
            has_index = unidoc_ocr.check_index(CROSSDOMAIN_KEY)

        if not has_index:
            print(f"[ERROR] Index for '{args.method}' (crossdomain) is empty. Run with --build-index first.")
            return

    print(f"\nRunning evaluation: method={args.method}  pool=cross-domain  top_k={args.top_k}")
    run_experiment(
        samples=all_samples,
        method=args.method,
        top_k=args.top_k,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    main()
