"""
离线检索评测脚本：在 MS-COCO 子集上对不同方法进行对比实验。

使用方式示例（在项目根目录）：

    python -m evaluation.run_offline_eval \\
        --dataset-path data/coco_subset_eval.json \\
        --method proposed \\
        --top-k 10

其中 data/coco_subset_eval.json 需按 datasets.coco_subset 中约定的格式准备。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 加载 backend/.env，确保从任意工作目录运行时配置都能正确读取
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from typing import List

from evaluation.datasets.coco_subset import CocoQuerySample, load_coco_subset
from evaluation.metrics import (
    RankedList,
    mean_average_precision,
    mean_recall_at_k,
    mean_reciprocal_rank,
)
from evaluation.methods import proposed_multimodal_rag, baseline_clip_retrieval, baseline_ocr_rag


def run_experiment(samples: List[CocoQuerySample], method: str, top_k: int) -> None:
    ranked_list: List[RankedList] = []

    for sample in samples:
        if method == "proposed":
            predicted_ids = proposed_multimodal_rag.retrieve(sample.query, top_k=top_k)
        elif method == "baseline_clip":
            predicted_ids = baseline_clip_retrieval.retrieve(sample.query, top_k=top_k)
        elif method == "baseline_ocr":
            predicted_ids = baseline_ocr_rag.retrieve(sample.query, top_k=top_k)
        else:
            raise ValueError(f"Unsupported method: {method}")

        ranked_list.append(RankedList(predicted_ids=predicted_ids, relevant_ids=sample.relevant_ids))

    print(f"Total queries evaluated: {len(ranked_list)}")
    for k in (1, 5, top_k):
        r = mean_recall_at_k(ranked_list, k)
        print(f"Recall@{k}: {r:.4f}")

    mrr = mean_reciprocal_rank(ranked_list)
    map_ = mean_average_precision(ranked_list, k=top_k)
    print(f"MRR: {mrr:.4f}")
    print(f"mAP@{top_k}: {map_:.4f}")


def main() -> None:
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
    args = parser.parse_args()

    path = Path(args.dataset_path)
    samples = load_coco_subset(path)
    if not samples:
        print("No samples loaded from dataset, please check dataset-path.")
        return

    run_experiment(samples, method=args.method, top_k=args.top_k)


if __name__ == "__main__":
    main()

