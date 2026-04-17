from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping, Optional


def resolve_effective_relevance_score(
    payload: Mapping[str, Any],
    metadata: Optional[Mapping[str, Any]] = None,
) -> tuple[Optional[float], str]:
    merged_metadata = metadata or {}

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
    filtered: list[MutableMapping[str, Any]] = []
    for item in items:
        annotate_relevance(item, metadata_key=metadata_key)
        metadata = item.get(metadata_key) if isinstance(item.get(metadata_key), Mapping) else None
        if passes_relevance_filter(item, enabled=enabled, min_score=min_score, metadata=metadata):
            filtered.append(item)
    return filtered
