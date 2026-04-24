"""
聊天回答的段落级引用对齐。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, List

from app.application.schemas import ChatCitationChunkRef, ChatCitationItem, ChatSourceItem


_ASCII_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-/.]{1,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

_MIN_PARAGRAPH_TEXT_LEN = 12
_MIN_OVERLAP = 2
_MIN_CONFIDENCE = 0.22
_MAX_SOURCE_IDS_PER_PARAGRAPH = 2


def split_markdown_blocks(content: str) -> list[str]:
    """按空行和 fenced code block 近似切分 Markdown 块。"""
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return []

    blocks: list[str] = []
    current: list[str] = []
    in_fence = False

    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            current.append(line)
            in_fence = not in_fence
            continue

        if not in_fence and not line.strip():
            if any(item.strip() for item in current):
                blocks.append("\n".join(current).strip())
                current = []
            continue

        current.append(line)

    if any(item.strip() for item in current):
        blocks.append("\n".join(current).strip())

    return blocks


def _normalize_text(value: str) -> str:
    normalized = str(value or "").lower()
    normalized = re.sub(r"[*_`>#\-\[\](){}|]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _collect_cjk_ngrams(text: str) -> Iterable[str]:
    chars = [char for char in text if _CJK_RE.match(char)]
    for size in (2, 3):
        for index in range(0, max(len(chars) - size + 1, 0)):
            yield "".join(chars[index:index + size])


def _build_term_counter(text: str) -> Counter[str]:
    normalized = _normalize_text(text)
    terms: Counter[str] = Counter()
    for token in _ASCII_TOKEN_RE.findall(normalized):
        if len(token) >= 3:
            terms[token] += 1
    for token in _collect_cjk_ngrams(normalized):
        terms[token] += 1
    return terms


def _build_source_text(source: ChatSourceItem) -> str:
    metadata = source.metadata or {}
    parts = [
        source.title or "",
        source.content or "",
        str(metadata.get("file_name") or ""),
        str(metadata.get("filename") or ""),
        str(metadata.get("doc_id") or ""),
        str(metadata.get("asset_type") or ""),
    ]
    return "\n".join(part for part in parts if str(part).strip())


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> tuple[float, int]:
    if not left or not right:
        return 0.0, 0

    overlap_terms = set(left.keys()) & set(right.keys())
    if not overlap_terms:
        return 0.0, 0

    dot = sum(left[token] * right[token] for token in overlap_terms)
    norm_left = math.sqrt(sum(value * value for value in left.values()))
    norm_right = math.sqrt(sum(value * value for value in right.values()))
    if norm_left == 0 or norm_right == 0:
        return 0.0, 0
    return dot / (norm_left * norm_right), len(overlap_terms)


def _build_chunk_refs(source: ChatSourceItem) -> list[ChatCitationChunkRef]:
    metadata = source.metadata or {}
    doc_id = metadata.get("doc_id")
    chunk_index = metadata.get("chunk_index")
    if doc_id is None or chunk_index is None:
        return []
    try:
        return [
            ChatCitationChunkRef(
                doc_id=str(doc_id),
                chunk_index=int(chunk_index),
                page_number=int(metadata["page_number"]) if metadata.get("page_number") is not None else None,
            )
        ]
    except (TypeError, ValueError):
        return []


def build_chat_citations(answer: str, sources: List[ChatSourceItem]) -> list[ChatCitationItem]:
    """对最终回答做轻量后处理，映射段落到高置信来源。"""
    if not answer or not sources:
        return []

    prepared_sources: list[tuple[ChatSourceItem, Counter[str]]] = []
    for source in sources:
        source_terms = _build_term_counter(_build_source_text(source))
        if source_terms:
            prepared_sources.append((source, source_terms))

    if not prepared_sources:
        return []

    citations: list[ChatCitationItem] = []
    for paragraph_index, paragraph in enumerate(split_markdown_blocks(answer)):
        plain_text = re.sub(r"[#>*`\-\[\]()]"," ", paragraph)
        if len(_normalize_text(plain_text)) < _MIN_PARAGRAPH_TEXT_LEN:
            continue

        paragraph_terms = _build_term_counter(paragraph)
        if not paragraph_terms:
            continue

        matches: list[tuple[float, int, ChatSourceItem]] = []
        for source, source_terms in prepared_sources:
            confidence, overlap_count = _cosine_similarity(paragraph_terms, source_terms)
            if overlap_count < _MIN_OVERLAP or confidence < _MIN_CONFIDENCE:
                continue
            matches.append((confidence, overlap_count, source))

        if not matches:
            continue

        matches.sort(key=lambda item: (item[0], item[1], item[2].relevance_score or item[2].score or 0.0), reverse=True)
        selected = matches[:_MAX_SOURCE_IDS_PER_PARAGRAPH]
        source_ids = [match[2].source_id for match in selected]
        doc_chunk_refs: list[ChatCitationChunkRef] = []
        for _, _, source in selected:
            doc_chunk_refs.extend(_build_chunk_refs(source))

        citations.append(
            ChatCitationItem(
                paragraph_key=f"p-{paragraph_index}",
                paragraph_index=paragraph_index,
                source_ids=source_ids,
                doc_chunk_refs=doc_chunk_refs,
                confidence=round(selected[0][0], 4),
            )
        )

    return citations
