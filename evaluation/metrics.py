"""
检索评测指标实现：Recall@K、mAP、MRR 等。

该模块独立于具体模型实现，只依赖预测结果 ID 列表与
每条查询的 ground truth 相关 ID 集合。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set


@dataclass
class RankedList:
    """单条查询的排序结果与相关集合。"""

    predicted_ids: List[str]
    relevant_ids: Set[str]


def recall_at_k(ranked: RankedList, k: int) -> float:
    if not ranked.relevant_ids:
        return 0.0
    top_k = ranked.predicted_ids[:k]
    hit = sum(1 for pid in top_k if pid in ranked.relevant_ids)
    return hit / len(ranked.relevant_ids)


def average_precision(ranked: RankedList, k: int | None = None) -> float:
    """AP@K，若 k 为 None 则使用完整列表长度。"""
    if not ranked.relevant_ids:
        return 0.0
    if k is None:
        k = len(ranked.predicted_ids)

    hits = 0
    sum_precisions = 0.0
    for idx, pid in enumerate(ranked.predicted_ids[:k], start=1):
        if pid in ranked.relevant_ids:
            hits += 1
            sum_precisions += hits / idx
    if hits == 0:
        return 0.0
    return sum_precisions / hits


def reciprocal_rank(ranked: RankedList) -> float:
    """MRR 的单样本 RR。"""
    for idx, pid in enumerate(ranked.predicted_ids, start=1):
        if pid in ranked.relevant_ids:
            return 1.0 / idx
    return 0.0


def mean_recall_at_k(rankeds: Iterable[RankedList], k: int) -> float:
    values = [recall_at_k(r, k) for r in rankeds]
    return sum(values) / len(values) if values else 0.0


def mean_average_precision(rankeds: Iterable[RankedList], k: int | None = None) -> float:
    values = [average_precision(r, k) for r in rankeds]
    return sum(values) / len(values) if values else 0.0


def mean_reciprocal_rank(rankeds: Iterable[RankedList]) -> float:
    values = [reciprocal_rank(r) for r in rankeds]
    return sum(values) / len(values) if values else 0.0

