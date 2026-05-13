"""
检索评测指标实现：Recall@K、mAP、MRR 等。

该模块独立于具体模型实现，只依赖预测结果 ID 列表与
每条查询的 ground truth 相关 ID 集合。

提供的指标：
  - Recall@K：前 K 个结果中命中的相关文档比例
  - AP@K（Average Precision）：考虑排序位置的精确率加权平均
  - RR（Reciprocal Rank）：第一个相关结果排名的倒数
  - 对应的宏观平均版本：mRecall、mAP、MRR
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set


@dataclass
class RankedList:
    """单条查询的排序结果与相关集合。

    Attributes:
        predicted_ids: 检索系统返回的排序结果 ID 列表（按相关度降序）。
        relevant_ids: 该查询的 ground truth 相关文档 ID 集合。
    """

    predicted_ids: List[str]
    relevant_ids: Set[str]


# ---- 单样本指标 ----

def recall_at_k(ranked: RankedList, k: int) -> float:
    """计算 Recall@K：前 K 个结果中命中的相关文档数 / 相关文档总数。

    Args:
        ranked: 单条查询的排序结果。
        k: 截断位置。

    Returns:
        Recall@K 值，范围 [0, 1]。无相关文档时返回 0。
    """
    if not ranked.relevant_ids:
        return 0.0
    top_k = ranked.predicted_ids[:k]
    hit = sum(1 for pid in top_k if pid in ranked.relevant_ids)
    return hit / len(ranked.relevant_ids)


def average_precision(ranked: RankedList, k: int | None = None) -> float:
    """计算 AP@K（Average Precision at K）。

    在每个命中位置计算 Precision(i)，取平均值。
    若 k 为 None 则使用完整列表长度。

    Args:
        ranked: 单条查询的排序结果。
        k: 截断位置，None 表示使用完整列表。

    Returns:
        AP@K 值，范围 [0, 1]。无相关文档或无命中时返回 0。
    """
    if not ranked.relevant_ids:
        return 0.0
    if k is None:
        k = len(ranked.predicted_ids)

    hits = 0
    sum_precisions = 0.0
    for idx, pid in enumerate(ranked.predicted_ids[:k], start=1):
        if pid in ranked.relevant_ids:
            hits += 1
            sum_precisions += hits / idx  # Precision@idx = hits / idx
    if hits == 0:
        return 0.0
    return sum_precisions / hits


def reciprocal_rank(ranked: RankedList) -> float:
    """计算 RR（Reciprocal Rank）：第一个相关结果排名的倒数。

    用于 MRR 指标的单样本计算。

    Args:
        ranked: 单条查询的排序结果。

    Returns:
        RR 值，范围 (0, 1]。未命中任何相关文档时返回 0。
    """
    for idx, pid in enumerate(ranked.predicted_ids, start=1):
        if pid in ranked.relevant_ids:
            return 1.0 / idx
    return 0.0


# ---- 宏观平均指标 ----

def mean_recall_at_k(rankeds: Iterable[RankedList], k: int) -> float:
    """计算 mRecall@K：多条查询的 Recall@K 宏观平均。

    Args:
        rankeds: 多条查询的排序结果迭代器。
        k: 截断位置。

    Returns:
        平均 Recall@K 值。无数据时返回 0。
    """
    values = [recall_at_k(r, k) for r in rankeds]
    return sum(values) / len(values) if values else 0.0


def mean_average_precision(rankeds: Iterable[RankedList], k: int | None = None) -> float:
    """计算 mAP@K：多条查询的 AP@K 宏观平均。

    Args:
        rankeds: 多条查询的排序结果迭代器。
        k: 截断位置，None 表示使用完整列表。

    Returns:
        平均 AP@K 值。无数据时返回 0。
    """
    values = [average_precision(r, k) for r in rankeds]
    return sum(values) / len(values) if values else 0.0


def mean_reciprocal_rank(rankeds: Iterable[RankedList]) -> float:
    """计算 MRR：多条查询的 RR 宏观平均。

    Args:
        rankeds: 多条查询的排序结果迭代器。

    Returns:
        平均 RR 值。无数据时返回 0。
    """
    values = [reciprocal_rank(r) for r in rankeds]
    return sum(values) / len(values) if values else 0.0

