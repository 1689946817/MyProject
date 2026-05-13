"""
离线检索评测脚本：在 MS-COCO 子集上对不同方法进行对比实验。

支持的方法：
  - proposed：基于 MLLM 图片描述的文本向量检索（本文方法）
  - baseline_clip：基于多模态 embedding 的检索
  - baseline_ocr：基于 OCR 文本的向量检索

使用方式示例（在项目根目录）：

    python -m evaluation.run_offline_eval \
        --dataset-path data/coco_subset_eval.json \
        --method proposed \
        --top-k 10

其中 data/coco_subset_eval.json 需按 datasets.coco_subset 中约定的格式准备。

结果自动保存到 data/eval_results/{method}_{timestamp}.json，包含：
- 每条 query 的逐条指标（Recall@K、RR、AP、首次命中位置、延迟）
- 完整检索结果列表及命中标记
- 汇总统计（均值 + 标准差）
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path

# ---- 环境配置加载 ----
# 加载 backend/.env，确保从任意工作目录运行时配置都能正确读取
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from typing import Any, Dict, List

# ---- 模块导入 ----
from evaluation.datasets.coco_subset import CocoQuerySample, load_coco_subset
from evaluation.metrics import (
    RankedList,
    average_precision,
    mean_average_precision,
    mean_recall_at_k,
    mean_reciprocal_rank,
    recall_at_k,
    reciprocal_rank,
)
from evaluation.methods import baseline_clip_retrieval, baseline_ocr_rag, proposed_multimodal_rag


# ---- 辅助函数 ----

def _first_hit_rank(ranked: RankedList) -> int | None:
    """返回第一个相关结果的排名（1-based），未命中返回 None。

    用于快速判断检索系统将相关文档排在了第几位。
    """
    for idx, pid in enumerate(ranked.predicted_ids, start=1):
        if pid in ranked.relevant_ids:
            return idx
    return None


# ---- 核心评测逻辑 ----

def run_experiment(
    samples: List[CocoQuerySample],
    method: str,
    top_k: int,
    output_dir: Path | None = None,
) -> None:
    """执行单个方法的检索评测实验。

    遍历所有样本，调用对应方法的检索函数，计算每条 query 的逐条指标，
    最后汇总统计并保存结果到 JSON 文件。

    Args:
        samples: 待评测的样本列表。
        method: 评测方法名（proposed / baseline_clip / baseline_ocr）。
        top_k: 检索返回的 Top-K 数量。
        output_dir: 结果输出目录，默认 data/eval_results/。
    """
    ranked_list: List[RankedList] = []
    per_query_records: List[Dict[str, Any]] = []

    # ---- 逐条评测 ----
    for i, sample in enumerate(samples):
        t0 = time.perf_counter()

        # 根据方法调用对应的检索函数
        if method == "proposed":
            predicted_ids = proposed_multimodal_rag.retrieve(sample.query, top_k=top_k)
        elif method == "baseline_clip":
            predicted_ids = baseline_clip_retrieval.retrieve(sample.query, top_k=top_k)
        elif method == "baseline_ocr":
            predicted_ids = baseline_ocr_rag.retrieve(sample.query, top_k=top_k)
        else:
            raise ValueError(f"Unsupported method: {method}")

        latency_ms = (time.perf_counter() - t0) * 1000
        ranked = RankedList(predicted_ids=predicted_ids, relevant_ids=sample.relevant_ids)
        ranked_list.append(ranked)

        # 计算逐条指标
        fhr = _first_hit_rank(ranked)
        hit_flags = [pid in sample.relevant_ids for pid in predicted_ids]

        per_query_records.append({
            "query_index": i,
            "query": sample.query,
            "relevant_ids": list(sample.relevant_ids),
            "predicted_ids": predicted_ids,
            "hit_flags": hit_flags,  # 每个位置是否命中
            "hit_count": sum(hit_flags),
            "first_hit_rank": fhr,  # 第一个相关结果的位置
            "recall_at_1": recall_at_k(ranked, 1),
            "recall_at_5": recall_at_k(ranked, 5),
            f"recall_at_{top_k}": recall_at_k(ranked, top_k),
            "reciprocal_rank": reciprocal_rank(ranked),
            f"ap_at_{top_k}": average_precision(ranked, top_k),
            "latency_ms": round(latency_ms, 2),
        })

        print(f"  [{i+1}/{len(samples)}] RR={reciprocal_rank(ranked):.2f}  "
              f"first_hit={fhr}  latency={latency_ms:.0f}ms  query={sample.query[:60]}")

    # ---- 汇总统计 ----
    def _stats(values: List[float]) -> Dict[str, float]:
        """计算均值和标准差。"""
        mean = sum(values) / len(values) if values else 0.0
        std = statistics.stdev(values) if len(values) > 1 else 0.0
        return {"mean": round(mean, 4), "std": round(std, 4)}

    latencies = [r["latency_ms"] for r in per_query_records]
    summary = {
        "method": method,
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

    # 打印汇总
    print(f"\n{'='*50}")
    print(f"Method: {method}  |  Queries: {summary['num_queries']}  |  Top-K: {top_k}")
    print(f"{'='*50}")
    for k in (1, 5, top_k):
        key = f"recall_at_{k}"
        s = summary[key]
        print(f"Recall@{k}:   {s['mean']:.4f}  (+-{s['std']:.4f})")
    print(f"MRR:         {summary['mrr']['mean']:.4f}  (+-{summary['mrr']['std']:.4f})")
    print(f"mAP@{top_k}:     {summary[f'map_at_{top_k}']['mean']:.4f}  (+-{summary[f'map_at_{top_k}']['std']:.4f})")
    print(f"Latency(ms): mean={summary['latency_ms']['mean']:.1f}  "
          f"median={summary['latency_ms_median']:.1f}  std={summary['latency_ms']['std']:.1f}")

    # ---- 保存结果到 JSON ----
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "data" / "eval_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{method}_{timestamp}.json"

    # 结果文件结构：summary（汇总）+ per_query（逐条）+ meta（元信息）
    result = {
        "summary": summary,
        "per_query": per_query_records,
        "meta": {
            "timestamp": timestamp,
            "method": method,
            "top_k": top_k,
        },
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存到: {output_path}")


# ---- 命令行入口 ----

def main() -> None:
    """命令行入口：解析参数、加载数据、执行评测。"""
    parser = argparse.ArgumentParser(description="Offline retrieval evaluation on COCO subset.")
    parser.add_argument("--dataset-path", type=str, required=True, help="Path to preprocessed COCO subset JSON.")
    parser.add_argument(
        "--method",
        type=str,
        choices=["proposed", "baseline_clip", "baseline_ocr"],
        default="proposed",
        help="Which method to evaluate.",
    )
    parser.add_argument("--top-k", type=int, default=10, help="Top-K for retrieval evaluation.")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save result JSON (default: data/eval_results/).")
    args = parser.parse_args()

    path = Path(args.dataset_path)
    samples = load_coco_subset(path)
    if not samples:
        print("No samples loaded from dataset, please check dataset-path.")
        return

    # baseline_ocr 需要 OCR 索引，提前检查
    if args.method == "baseline_ocr" and not baseline_ocr_rag.check_ocr_index():
        print(
            "[ERROR] OCR index is missing or unhealthy. Rebuild the `images_ocr_text` "
            "collection before running baseline_ocr evaluation."
        )
        return

    output_dir = Path(args.output_dir) if args.output_dir else None
    run_experiment(samples, method=args.method, top_k=args.top_k, output_dir=output_dir)


if __name__ == "__main__":
    main()
