"""
UniDoc-Bench-subset 跨领域混合候选池检索评测脚本。

功能概述：
    与 run_unidoc_eval.py（单领域评测）互补，本脚本将所有 8 个领域的候选图片
    合并为一个统一的混合候选池（cross-domain pool），每条 query 在全量候选中检索。

    这种设定更贴近真实应用场景——用户提问时，系统并不预知图片属于哪个领域，
    检索范围必须覆盖全部已入库的图片。

评测方法：
    同 run_unidoc_eval.py，支持三种方法的对比：
    - proposed:      MLLM 描述 → 文本 Embedding 检索（本文方法）
    - baseline_clip:  多模态 Embedding 直接检索（基线方法）
    - baseline_ocr:   OCR 文本 → 文本 Embedding 检索（基线方法）

关键差异（与 run_unidoc_eval.py 相比）：
    - 候选池：单领域 → 跨领域全部合并
    - 索引命名：unidoc_{domain}_xxx → unidoc_crossdomain_xxx
    - 结果文件：unidoc_{domain}_xxx → unidoc_crossdomain_xxx
    - 分组统计：额外增加了 by_domain 维度，可分析各领域在混合池中的表现
    - 加载数据：load_unidoc_domain 遍历所有 DOMAINS，get_all_image_records 获取全量图片

候选池合并策略：
    所有 8 个领域的图片记录通过 get_all_image_records() 合并，
    然后构建一个名为 unidoc_crossdomain_{method} 的 ChromaDB 集合。

缓存复用：
    proposed 方法可复用已有数据集的描述缓存（--reuse-cache-dataset），
    避免为跨领域实验重复调用 MLLM。默认复用 "UniDoc-Bench-subset" 缓存。

使用示例（从项目根目录）：

    # 使用 proposed 方法在混合候选池中评测
    python -m evaluation.run_unidoc_full_eval \\
        --method proposed \\
        --top-k 10 \\
        --build-index

    # 复用额外的缓存数据集
    python -m evaluation.run_unidoc_full_eval \\
        --method proposed \\
        --reuse-cache-dataset UniDoc-Bench-full \\
        --build-index

结果文件：
    保存到 data/eval_results/unidoc_crossdomain_{method}_{timestamp}.json
    除单领域评测的字段外，额外包含：
    - by_domain: 按原始领域分组的指标，用于分析领域间检索难度差异
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

# ──────────────────────────────────────────────────────────────────────
# 环境配置加载（同 run_unidoc_eval.py）
# ──────────────────────────────────────────────────────────────────────
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from evaluation.datasets.unidoc_subset import (  # noqa: E402
    DOMAINS,                # 8 个领域名称列表
    UniDocQuerySample,      # query 样本数据类
    get_all_image_records,  # 加载全领域候选图片（区别于单领域的 get_domain_image_records）
    load_unidoc_domain,     # 加载某领域的 query 样本
)
from evaluation.metrics import (  # noqa: E402
    RankedList,             # 排序结果数据类
    average_precision,      # AP 指标
    recall_at_k,            # Recall@K 指标
    reciprocal_rank,        # RR 指标
)
from evaluation.methods import unidoc_clip, unidoc_ocr, unidoc_proposed  # noqa: E402

# 跨领域实验使用虚拟 domain key "crossdomain"，
# 用于 ChromaDB 集合命名（如 unidoc_crossdomain_proposed）
CROSSDOMAIN_KEY = "crossdomain"

# 默认复用的 proposed 缓存数据集名称列表
# 跨领域实验可复用单领域实验已生成的 MLLM 描述缓存，避免重复调用 API
DEFAULT_REUSE_CACHE_DATASETS = ["UniDoc-Bench-subset"]


# ──────────────────────────────────────────────────────────────────────
# 工具函数（与 run_unidoc_eval.py 功能相同）
# ──────────────────────────────────────────────────────────────────────

def _configure_utf8_stdio() -> None:
    """将 stdout/stderr 重新配置为 UTF-8 编码。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_stdio()


def _safe_console_text(text: str) -> str:
    """编码清洗，替换终端无法表示的字符。"""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _print_safe(*parts: object, sep: str = " ", end: str = "\n") -> None:
    """安全打印。"""
    message = sep.join(str(part) for part in parts)
    print(_safe_console_text(message), end=end)


def _first_hit_rank(ranked: RankedList) -> int | None:
    """返回排序列表中第一个命中的排名位置（1-based），无命中返回 None。"""
    for idx, pid in enumerate(ranked.predicted_ids, start=1):
        if pid in ranked.relevant_ids:
            return idx
    return None


def _stats(values: List[float]) -> Dict[str, float]:
    """计算均值和标准差，返回 {"mean": ..., "std": ...}。"""
    mean = sum(values) / len(values) if values else 0.0
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"mean": round(mean, 4), "std": round(std, 4)}


def _group_stats(records: List[Dict], group_key: str, top_k: int) -> Dict[str, Any]:
    """按指定字段分组统计检索指标。

    本脚本中用于按 domain / question_type / answer_type 三个维度分组。
    """
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


# ──────────────────────────────────────────────────────────────────────
# 核心评测逻辑
# ──────────────────────────────────────────────────────────────────────

def run_experiment(
    samples: List[UniDocQuerySample],
    method: str,
    top_k: int,
    output_dir: Path,
) -> None:
    """执行跨领域混合候选池检索评测实验。

    与单领域评测的区别：
    - 不接收 domain 参数，所有 query 统一在 CROSSDOMAIN_KEY 索引中检索
    - samples 包含所有 8 个领域的 query
    - 额外生成 by_domain 分组统计，分析各领域在混合池中的表现

    Args:
        samples: 全部领域的 query 样本列表（跨领域合并）。
        method: 评测方法，"proposed" / "baseline_clip" / "baseline_ocr"。
        top_k: 返回的检索结果数量上限。
        output_dir: 结果 JSON 文件的输出目录。
    """
    ranked_list: List[RankedList] = []
    per_query_records: List[Dict[str, Any]] = []

    for i, sample in enumerate(samples):
        t0 = time.perf_counter()

        # 所有 query 都在跨领域混合索引中检索
        # domain 参数统一使用 CROSSDOMAIN_KEY（"crossdomain"）
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
    # ── 汇总统计：跨领域混合池的整体指标 ──
    summary = {
        "method": method,
        "domain": "all (cross-domain pool)",  # 跨领域评测固定标记
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

    # ── 分组统计：跨领域评测额外增加 by_domain 维度 ──
    # 可分析各领域在混合池中的检索难度差异（如 finance 是否比 energy 更难检索）
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

    # ── 保存结果到 JSON 文件 ──
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 跨领域结果文件统一以 "crossdomain" 标识
    output_path = output_dir / f"unidoc_crossdomain_{method}_{timestamp}.json"

    result = {
        "summary": summary,
        "by_domain": by_domain,          # 跨领域评测特有：按原始领域分组
        "by_question_type": by_question_type,
        "by_answer_type": by_answer_type,
        "per_query": per_query_records,
        "meta": {
            "timestamp": timestamp,
            "method": method,
            "domain": "all",
            "top_k": top_k,
            "dataset_name": "UniDoc-Bench-subset",
            "candidate_pool": "cross_domain_all_subset",  # 标记候选池类型
        },
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_safe(f"\n结果已保存到: {output_path}")


def main() -> None:
    """命令行入口：加载全部领域数据、构建跨领域索引、执行评测。"""
    parser = argparse.ArgumentParser(
        description="Offline retrieval evaluation on cross-domain merged pool from UniDoc-Bench-subset."
    )
    parser.add_argument(
        "--method",
        type=str,
        choices=["proposed", "baseline_clip", "baseline_ocr"],
        default="proposed",
        help="评测方法（默认 proposed）",
    )
    parser.add_argument("--top-k", type=int, default=10, help="检索返回的结果数量")
    parser.add_argument("--build-index", action="store_true", help="评测前先构建跨领域合并索引")
    parser.add_argument("--dataset-root", type=str, default="data/UniDoc-Bench-subset", help="数据集根目录")
    parser.add_argument("--output-dir", type=str, default="data/eval_results", help="结果输出目录")
    parser.add_argument("--dataset-name", type=str, default="UniDoc-Bench-crossdomain",
                        help="本次实验的数据集标识名（用于 proposed 缓存签名）")
    parser.add_argument("--cache-dir", type=str, default="data/cache/unidoc_proposed", help="proposed 缓存目录")
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="复用已成功的 proposed 缓存记录（默认开启）。",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="重试之前失败的 proposed 缓存记录。",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="忽略已有缓存，强制重新生成所有 MLLM 描述。",
    )
    parser.add_argument(
        "--reuse-cache-dataset",
        action="append",
        default=None,
        help="额外复用的 proposed 缓存 dataset_name，可多次指定。"
             "用于跨领域实验复用单领域实验已生成的缓存，减少 MLLM 调用。",
    )
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root)
    output_dir = Path(args.output_dir)
    # 如果未指定 --reuse-cache-dataset，默认复用 "UniDoc-Bench-subset" 缓存
    reuse_cache_datasets = args.reuse_cache_dataset or DEFAULT_REUSE_CACHE_DATASETS

    # ── 加载全部领域 query ──
    # 遍历 DOMAINS 列表中的 8 个领域，逐个加载 query 样本并合并
    all_samples: List[UniDocQuerySample] = []
    for domain in DOMAINS:
        try:
            domain_samples = load_unidoc_domain(domain, dataset_root)
            all_samples.extend(domain_samples)
            print(f"  Loaded {len(domain_samples)} queries from domain '{domain}'")
        except FileNotFoundError as e:
            print(f"  [SKIP] {e}")
    print(f"Total queries: {len(all_samples)}")

    # ── 构建或验证跨领域索引 ──
    if args.build_index:
        print(f"\nBuilding cross-domain merged candidate pool...")
        # get_all_image_records: 获取所有 8 个领域的图片记录，合并为一个大候选池
        image_records = get_all_image_records(dataset_root)
        print(f"Total candidate images: {len(image_records)}")

        if args.method == "proposed":
            # proposed 方法：复用已有缓存 + 跨领域索引构建
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
                CROSSDOMAIN_KEY,       # 索引使用 "crossdomain" 作为 domain key
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
        # 未指定 --build-index 时，验证索引是否存在
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
