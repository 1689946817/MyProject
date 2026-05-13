"""
相关性评分过滤模块

提供检索结果的相关性评分标注与过滤功能：
- resolve_effective_relevance_score: 从多个分数来源中解析最优先的相关性分数
- annotate_relevance: 将评分信息写入 payload 的 metadata 中
- filter_by_relevance: 根据 rerank 分数阈值过滤低相关性结果
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping, Optional


def resolve_effective_relevance_score(
    payload: Mapping[str, Any],
    metadata: Optional[Mapping[str, Any]] = None,
) -> tuple[Optional[float], str]:
    """从多个分数来源中解析最优先的相关性分数。

    优先级：relevance_score > rerank_score > rrf_score > vector score。
    返回 (分数值, 分数来源标识)。

    Args:
        payload: 检索结果字典（顶层字段优先）
        metadata: 元数据字典（作为 fallback 来源）

    Returns:
        (分数值或 None, 分数来源字符串)
    """
    merged_metadata = metadata or {}

    # 按优先级依次尝试：显式 relevance_score → rerank → rrf → vector
    candidates = (
        (
            str(payload.get("score_source") or merged_metadata.get("score_source") or "explicit"),
            payload.get("relevance_score", merged_metadata.get("relevance_score")),
        ),
        ("rerank", payload.get("rerank_score", merged_metadata.get("rerank_score"))),
        ("rrf", payload.get("rrf_score", merged_metadata.get("rrf_score"))),
        ("vector", payload.get("score", merged_metadata.get("score"))),
    )
    for source, value in candidates:
        if value is None:
            continue
        try:
            return float(value), source
        except (TypeError, ValueError):
            continue
    return None, "unknown"


def annotate_relevance(
    payload: MutableMapping[str, Any],
    metadata_key: str = "metadata",
) -> MutableMapping[str, Any]:
    """将相关性评分标注到 payload 顶层和 metadata 中。

    确保 payload 和 metadata 中都包含 relevance_score 和 score_source 字段。
    """
    raw_metadata = payload.get(metadata_key)
    metadata: MutableMapping[str, Any]
    if isinstance(raw_metadata, MutableMapping):
        metadata = raw_metadata
    elif isinstance(raw_metadata, Mapping):
        metadata = dict(raw_metadata)
        payload[metadata_key] = metadata
    else:
        metadata = {}
        payload[metadata_key] = metadata

    relevance_score, score_source = resolve_effective_relevance_score(payload, metadata)
    payload["relevance_score"] = relevance_score
    payload["score_source"] = score_source
    metadata["relevance_score"] = relevance_score
    metadata["score_source"] = score_source
    return payload


def passes_relevance_filter(
    payload: Mapping[str, Any],
    *,
    enabled: bool,
    min_score: Optional[float],
    metadata: Optional[Mapping[str, Any]] = None,
) -> bool:
    """判断单条结果是否通过相关性阈值过滤。

    仅当 rerank_score 存在时才执行阈值过滤；
    无 rerank_score 的 fallback 路径保留结果不被过滤。
    """
    if not enabled:
        return True

    effective_min_score = 0.0 if min_score is None else float(min_score)
    merged_metadata = metadata or {}
    rerank_score = payload.get("rerank_score", merged_metadata.get("rerank_score"))
    if rerank_score is None:
        # Only rerank_score participates in threshold filtering.
        # Fallback-only paths skip filtering instead of dropping results.
        return True
    try:
        return float(rerank_score) >= effective_min_score
    except (TypeError, ValueError):
        return True


def filter_by_relevance(
    items: Iterable[MutableMapping[str, Any]],
    *,
    enabled: bool,
    min_score: Optional[float],
    metadata_key: str = "metadata",
) -> list[MutableMapping[str, Any]]:
    """批量过滤：先标注相关性评分，再按阈值过滤。"""
    filtered: list[MutableMapping[str, Any]] = []
    for item in items:
        annotate_relevance(item, metadata_key=metadata_key)
        metadata = item.get(metadata_key) if isinstance(item.get(metadata_key), Mapping) else None
        if passes_relevance_filter(item, enabled=enabled, min_score=min_score, metadata=metadata):
            filtered.append(item)
    return filtered
