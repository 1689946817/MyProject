"""
PDF 文档解析工具

双通道解析：
- 文本通道：PyMuPDFLoader 负责页级文本文档化
- 视觉通道：PyMuPDF 负责嵌入图提取和表格页整页渲染
"""
from __future__ import annotations

import os
import re
import tempfile
import html
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Type

import fitz  # PyMuPDF
from langchain_core.documents import Document

from app.core.config import settings


DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100
DEFAULT_PDF_RENDER_DPI = 150
DEFAULT_TABLE_CROP_PADDING = 12
DEFAULT_TABLE_NEARBY_TEXT_MARGIN = 120
DEFAULT_TABLE_NEARBY_TEXT_MIN_CHARS = 8
DEFAULT_SMALL_TABLE_AREA_RATIO = 0.12
DEFAULT_CONTINUATION_BOTTOM_RATIO = 0.85
DEFAULT_CONTINUATION_TOP_RATIO = 0.15
DEFAULT_TABLE_WIDTH_TOLERANCE_RATIO = 0.08
DEFAULT_TABLE_CENTER_TOLERANCE_RATIO = 0.06
DEFAULT_MIN_EMBEDDED_IMAGE_DIMENSION = 96
DEFAULT_MIN_EMBEDDED_IMAGE_AREA = 12_000
DEFAULT_MIN_EMBEDDED_IMAGE_PAGE_RATIO = 0.015
DEFAULT_MIN_EMBEDDED_IMAGE_BYTES = 2_048
DEFAULT_MIN_RENDERED_IMAGE_DIMENSION = 120
DEFAULT_MIN_RENDERED_IMAGE_AREA_RATIO = 0.02
DEFAULT_PAGE_RENDER_MIN_FILTERED_IMAGE_COUNT = 6
DEFAULT_PAGE_RENDER_MIN_FILTERED_AREA_RATIO = 0.1
DEFAULT_MAX_EMBEDDED_IMAGES_PER_PAGE = 4
DEFAULT_FRAGMENTED_IMAGE_MAX_DIMENSION = 64

# 中英文句子结束符
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?\n])\s*")
_HTML_TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)
_HTML_TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_HTML_CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_LATEX_COMMAND_RE = re.compile(r"\\([a-zA-Z]+)\s*(?:\{([^{}]*)\})?")


@dataclass
class ParsedPdfTextChunk:
    """标准化 PDF 文本片段。"""

    content: str
    page_number: int
    chunk_index: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedPdfVisualAsset:
    """标准化 PDF 视觉资产。"""

    image_bytes: bytes
    page_number: int
    asset_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def _get_pdf_text_loader_cls() -> Type[Any]:
    """惰性导入 loader，避免模块导入时拉起重依赖。"""
    from langchain_community.document_loaders import PyMuPDFLoader

    return PyMuPDFLoader


def _sentence_aware_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """按句子边界切分文本，合并至 chunk_size 以内。"""
    if not text.strip():
        return []

    sentences = _SENTENCE_SPLIT_RE.split(text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return []

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for sent in sentences:
        sent_len = len(sent)
        if sent_len > chunk_size:
            if current_chunk:
                chunks.append("".join(current_chunk))
                current_chunk = []
                current_len = 0
            chunks.append(sent)
            continue

        if current_len + sent_len > chunk_size and current_chunk:
            chunks.append("".join(current_chunk))
            overlap_chunk: List[str] = []
            overlap_len = 0
            for previous_sentence in reversed(current_chunk):
                if overlap_len + len(previous_sentence) > overlap:
                    break
                overlap_chunk.insert(0, previous_sentence)
                overlap_len += len(previous_sentence)
            current_chunk = overlap_chunk
            current_len = overlap_len

        current_chunk.append(sent)
        current_len += sent_len

    if current_chunk:
        chunks.append("".join(current_chunk))

    return chunks


def extract_pdf_text_documents(file_path: str, file_name: str | None = None) -> List[Document]:
    """使用 PyMuPDFLoader 抽取页级文档，并规范化 metadata。"""
    if settings.PDF_TEXT_LOADER_BACKEND != "pymupdf":
        raise ValueError(
            f"Unsupported PDF text loader backend: {settings.PDF_TEXT_LOADER_BACKEND}"
        )

    loader_cls = _get_pdf_text_loader_cls()
    loader = loader_cls(file_path)
    documents = loader.load()

    normalized: List[Document] = []
    fallback_name = file_name or os.path.basename(file_path)
    for doc in documents:
        meta = dict(doc.metadata or {})
        page_number = int(meta.get("page", 0)) + 1
        meta["page_number"] = page_number
        meta["file_name"] = fallback_name
        meta["source_type"] = "pdf_page"
        normalized.append(Document(page_content=doc.page_content, metadata=meta))
    return normalized


def build_pdf_text_chunks(
    documents: Sequence[Document],
    doc_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[ParsedPdfTextChunk]:
    """将页级文档切成标准化文本片段。"""
    chunks: List[ParsedPdfTextChunk] = []
    next_index = 0

    for doc in documents:
        page_number = int((doc.metadata or {}).get("page_number", 1))
        file_name = (doc.metadata or {}).get("file_name", "")
        for chunk_content in _sentence_aware_chunks(doc.page_content or "", chunk_size, chunk_overlap):
            metadata = {
                "doc_id": doc_id,
                "chunk_index": next_index,
                "page_number": page_number,
                "file_name": file_name,
                "source_type": "pdf_text_chunk",
            }
            chunks.append(
                ParsedPdfTextChunk(
                    content=chunk_content,
                    page_number=page_number,
                    chunk_index=next_index,
                    metadata=metadata,
                )
            )
            next_index += 1

    return chunks


def _strip_html_fragment(text: str) -> str:
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _convert_html_table_to_text(table_html: str) -> str:
    rows: List[str] = []
    for row_html in _HTML_TR_RE.findall(table_html):
        cells = [_strip_html_fragment(cell) for cell in _HTML_CELL_RE.findall(row_html)]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(" | ".join(cells))
    if rows:
        return "\n".join(rows)
    return _strip_html_fragment(table_html)


def normalize_mineru_markdown_for_chunking(markdown_text: str) -> str:
    """清洗 MinerU markdown 中混入的 HTML 表格，避免原始标签进入 chunk。"""
    if not markdown_text:
        return markdown_text

    cleaned = _MARKDOWN_IMAGE_RE.sub(" ", markdown_text)
    cleaned = cleaned.replace("", "\n- ").replace("•", "\n- ").replace("◦", "\n- ")
    cleaned = _HTML_TABLE_RE.sub(lambda match: f"\n{_convert_html_table_to_text(match.group(0))}\n", cleaned)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?(p|div|section|article|header|footer|ul|ol|li)\b[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?(span|strong|em|b|i|thead|tbody|tfoot|caption|colgroup|col)\b[^>]*>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = _LATEX_COMMAND_RE.sub(lambda m: "*" if m.group(1) == "star" else (m.group(2) or m.group(1)), cleaned)
    cleaned = cleaned.replace("$", " ")
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    cleaned = cleaned.replace("^", " ")
    cleaned = cleaned.replace("\\", " ")
    cleaned = html.unescape(cleaned).replace("\xa0", " ")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _get_page_dimensions(page: Any) -> Tuple[float, float]:
    rect = getattr(page, "rect", None)
    width = float(getattr(rect, "width", 0.0) or 0.0)
    height = float(getattr(rect, "height", 0.0) or 0.0)
    return width, height


def _normalize_bbox(
    bbox: Iterable[float],
    page_width: float,
    page_height: float,
    padding: int = DEFAULT_TABLE_CROP_PADDING,
) -> Optional[Tuple[float, float, float, float]]:
    try:
        x0, y0, x1, y1 = [float(value) for value in bbox]
    except (TypeError, ValueError):
        return None

    if x1 <= x0 or y1 <= y0:
        return None

    x0 = max(0.0, x0 - padding)
    y0 = max(0.0, y0 - padding)
    x1 = min(page_width, x1 + padding)
    y1 = min(page_height, y1 + padding)

    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _iter_page_text_blocks(page: Any) -> List[Tuple[float, float, float, float, str]]:
    try:
        blocks = page.get_text("blocks")
    except TypeError:
        blocks = page.get_text()
    except Exception:
        return []

    normalized: List[Tuple[float, float, float, float, str]] = []
    if not isinstance(blocks, list):
        return normalized
    for block in blocks:
        if not isinstance(block, (tuple, list)) or len(block) < 5:
            continue
        try:
            x0, y0, x1, y1 = [float(block[index]) for index in range(4)]
        except (TypeError, ValueError):
            continue
        text = str(block[4] or "").strip()
        if not text:
            continue
        normalized.append((x0, y0, x1, y1, text))
    return normalized


def _table_fallback_reason(
    page: Any,
    bbox: Tuple[float, float, float, float],
    table_count: int,
    page_width: float,
    page_height: float,
) -> Optional[str]:
    x0, y0, x1, y1 = bbox
    table_width = max(0.0, x1 - x0)
    table_height = max(0.0, y1 - y0)
    table_area = table_width * table_height
    page_area = max(page_width * page_height, 1.0)
    area_ratio = table_area / page_area

    if table_width <= 1 or table_height <= 1:
        return "invalid_bbox"
    if table_count == 1 and area_ratio < DEFAULT_SMALL_TABLE_AREA_RATIO:
        return "small_table_needs_context"

    vertical_margin = DEFAULT_TABLE_NEARBY_TEXT_MARGIN
    for bx0, by0, bx1, by1, text in _iter_page_text_blocks(page):
        if len(text) < DEFAULT_TABLE_NEARBY_TEXT_MIN_CHARS:
            continue
        horizontally_overlaps = not (bx1 < x0 or bx0 > x1)
        near_above = 0 <= (y0 - by1) <= vertical_margin
        near_below = 0 <= (by0 - y1) <= vertical_margin
        if horizontally_overlaps and (near_above or near_below):
            return "important_nearby_text"

    return None


def _group_cross_page_table_assets(
    assets: List[ParsedPdfVisualAsset],
    file_name: str,
) -> None:
    table_assets = [asset for asset in assets if asset.asset_type == "table_crop"]
    if len(table_assets) < 2:
        return

    table_assets.sort(
        key=lambda asset: (
            int(asset.page_number),
            int(asset.metadata.get("table_index_on_page", 0)),
        )
    )

    group_index = 0
    current_group_id: Optional[str] = None

    for previous, current in zip(table_assets, table_assets[1:]):
        if current.page_number != previous.page_number + 1:
            current_group_id = None
            continue

        prev_bbox = previous.metadata.get("_bbox")
        curr_bbox = current.metadata.get("_bbox")
        prev_height = float(previous.metadata.get("_page_height", 0.0) or 0.0)
        curr_height = float(current.metadata.get("_page_height", 0.0) or 0.0)
        prev_width = float(previous.metadata.get("_page_width", 0.0) or 0.0)
        curr_width = float(current.metadata.get("_page_width", 0.0) or 0.0)
        if not prev_bbox or not curr_bbox or prev_height <= 0 or curr_height <= 0:
            current_group_id = None
            continue

        prev_x0, _prev_y0, prev_x1, prev_y1 = prev_bbox
        curr_x0, curr_y0, curr_x1, _curr_y1 = curr_bbox
        prev_bottom_ratio = prev_y1 / prev_height
        curr_top_ratio = curr_y0 / curr_height
        prev_table_width = prev_x1 - prev_x0
        curr_table_width = curr_x1 - curr_x0
        prev_center = (prev_x0 + prev_x1) / 2
        curr_center = (curr_x0 + curr_x1) / 2
        width_tolerance = max(prev_width, curr_width, 1.0) * DEFAULT_TABLE_WIDTH_TOLERANCE_RATIO
        center_tolerance = max(prev_width, curr_width, 1.0) * DEFAULT_TABLE_CENTER_TOLERANCE_RATIO

        is_continuation = (
            prev_bottom_ratio >= DEFAULT_CONTINUATION_BOTTOM_RATIO
            and curr_top_ratio <= DEFAULT_CONTINUATION_TOP_RATIO
            and abs(prev_table_width - curr_table_width) <= width_tolerance
            and abs(prev_center - curr_center) <= center_tolerance
        )
        if not is_continuation:
            current_group_id = None
            continue

        if current_group_id is None:
            group_index += 1
            current_group_id = f"{file_name}:table-group:{group_index}"
            previous.metadata["table_group_id"] = current_group_id
            previous.metadata["continued_from_previous_page"] = bool(
                previous.metadata.get("continued_from_previous_page", False)
            )

        previous.metadata["continued_to_next_page"] = True
        current.metadata["table_group_id"] = current_group_id
        current.metadata["continued_from_previous_page"] = True
        current.metadata["continued_to_next_page"] = bool(
            current.metadata.get("continued_to_next_page", False)
        )


def _largest_image_rect(
    page: Any,
    xref: int,
    page_width: float,
    page_height: float,
) -> Optional[Tuple[float, float, float, float]]:
    try:
        rects = page.get_image_rects(xref)
    except Exception:
        return None

    candidates: List[Tuple[float, float, float, float]] = []
    for rect in rects or []:
        normalized = _normalize_bbox(
            (
                float(getattr(rect, "x0", 0.0) or 0.0),
                float(getattr(rect, "y0", 0.0) or 0.0),
                float(getattr(rect, "x1", 0.0) or 0.0),
                float(getattr(rect, "y1", 0.0) or 0.0),
            ),
            page_width,
            page_height,
            padding=0,
        )
        if normalized is not None:
            candidates.append(normalized)

    if not candidates:
        return None
    return max(candidates, key=lambda bbox: max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1]))


def _should_keep_embedded_image(
    base_image: Dict[str, Any],
    page_width: float,
    page_height: float,
    rendered_bbox: Optional[Tuple[float, float, float, float]] = None,
) -> bool:
    """过滤明显的装饰性小图标，保留更可能有知识价值的图片。"""
    image_bytes = base_image.get("image") or b""
    if not image_bytes:
        return False

    width = int(base_image.get("width") or 0)
    height = int(base_image.get("height") or 0)
    if width <= 0 or height <= 0:
        return True

    if width >= DEFAULT_MIN_EMBEDDED_IMAGE_DIMENSION and height >= DEFAULT_MIN_EMBEDDED_IMAGE_DIMENSION:
        return True

    area = width * height
    if area >= DEFAULT_MIN_EMBEDDED_IMAGE_AREA:
        return True

    page_area = max(page_width * page_height, 1.0)
    if area / page_area >= DEFAULT_MIN_EMBEDDED_IMAGE_PAGE_RATIO:
        return True

    if rendered_bbox is not None:
        rendered_width = max(0.0, rendered_bbox[2] - rendered_bbox[0])
        rendered_height = max(0.0, rendered_bbox[3] - rendered_bbox[1])
        rendered_area = rendered_width * rendered_height
        if (
            rendered_width >= DEFAULT_MIN_RENDERED_IMAGE_DIMENSION
            and rendered_height >= DEFAULT_MIN_RENDERED_IMAGE_DIMENSION
        ):
            return True
        if rendered_area / page_area >= DEFAULT_MIN_RENDERED_IMAGE_AREA_RATIO:
            return True

    if len(image_bytes) >= DEFAULT_MIN_EMBEDDED_IMAGE_BYTES and max(width, height) >= DEFAULT_MIN_EMBEDDED_IMAGE_DIMENSION:
        return True

    return False


def _should_add_page_render(
    kept_assets: Sequence[ParsedPdfVisualAsset],
    filtered_count: int,
    filtered_area_ratio: float,
) -> bool:
    if kept_assets:
        return False
    if filtered_count >= DEFAULT_PAGE_RENDER_MIN_FILTERED_IMAGE_COUNT:
        return True
    return filtered_area_ratio >= DEFAULT_PAGE_RENDER_MIN_FILTERED_AREA_RATIO


def _page_is_fragmented_embedded_visuals(
    kept_assets: Sequence[ParsedPdfVisualAsset],
    total_image_count: int,
) -> bool:
    if total_image_count < DEFAULT_PAGE_RENDER_MIN_FILTERED_IMAGE_COUNT or not kept_assets:
        return False
    return all(
        max(
            int(asset.metadata.get("image_width") or 0),
            int(asset.metadata.get("image_height") or 0),
        ) <= DEFAULT_FRAGMENTED_IMAGE_MAX_DIMENSION
        for asset in kept_assets
    )


def extract_pdf_visual_assets(
    file_bytes: bytes,
    file_name: str | None = None,
) -> List[ParsedPdfVisualAsset]:
    """提取 PDF 嵌入图片、表格裁图和必要时的整页兜底渲染。"""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    assets: List[ParsedPdfVisualAsset] = []
    seen_xrefs: set[int] = set()
    normalized_name = file_name or "document.pdf"

    for page_index, page in enumerate(doc):
        page_number = page_index + 1
        page_width, page_height = _get_page_dimensions(page)
        page_area = max(page_width * page_height, 1.0)
        embedded_candidates: List[ParsedPdfVisualAsset] = []
        filtered_embedded_count = 0
        filtered_embedded_area = 0.0
        page_image_count = 0

        for img_info in page.get_images(full=True):
            page_image_count += 1
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                rendered_bbox = _largest_image_rect(page, xref, page_width, page_height)
                if _should_keep_embedded_image(base_image, page_width, page_height, rendered_bbox):
                    metadata = {
                        "page_number": page_number,
                        "file_name": normalized_name,
                        "asset_type": "embedded_image",
                        "image_width": int(base_image.get("width") or 0),
                        "image_height": int(base_image.get("height") or 0),
                    }
                    if rendered_bbox is not None:
                        rendered_area = max(0.0, rendered_bbox[2] - rendered_bbox[0]) * max(0.0, rendered_bbox[3] - rendered_bbox[1])
                        metadata["_rendered_area"] = rendered_area
                    embedded_candidates.append(
                        ParsedPdfVisualAsset(
                            image_bytes=img_bytes,
                            page_number=page_number,
                            asset_type="embedded_image",
                            metadata=metadata,
                        )
                    )
                else:
                    filtered_embedded_count += 1
                    if rendered_bbox is not None:
                        filtered_embedded_area += max(0.0, rendered_bbox[2] - rendered_bbox[0]) * max(0.0, rendered_bbox[3] - rendered_bbox[1])
                    else:
                        filtered_embedded_area += float((base_image.get("width") or 0) * (base_image.get("height") or 0))
            except Exception:
                pass

        if _page_is_fragmented_embedded_visuals(embedded_candidates, page_image_count):
            for asset in embedded_candidates:
                filtered_embedded_count += 1
                filtered_embedded_area += float(asset.metadata.get("_rendered_area", 0.0) or 0.0)
            embedded_candidates = []

        embedded_candidates.sort(
            key=lambda asset: float(asset.metadata.get("_rendered_area", 0.0) or 0.0),
            reverse=True,
        )
        for asset in embedded_candidates[:DEFAULT_MAX_EMBEDDED_IMAGES_PER_PAGE]:
            assets.append(asset)

        if _should_add_page_render(
            kept_assets=embedded_candidates[:DEFAULT_MAX_EMBEDDED_IMAGES_PER_PAGE],
            filtered_count=filtered_embedded_count,
            filtered_area_ratio=filtered_embedded_area / page_area,
        ):
            try:
                page_pix = page.get_pixmap(dpi=DEFAULT_PDF_RENDER_DPI)
                assets.append(
                    ParsedPdfVisualAsset(
                        image_bytes=page_pix.tobytes("png"),
                        page_number=page_number,
                        asset_type="page_render",
                        metadata={
                            "page_number": page_number,
                            "file_name": normalized_name,
                            "asset_type": "page_render",
                            "fallback_reason": "fragmented_or_filtered_images",
                        },
                    )
                )
            except Exception:
                pass

        try:
            tables = page.find_tables()
            detected_tables = list(getattr(tables, "tables", []) or [])
            if detected_tables:
                fallback_reasons: List[str] = []

                for table_index, table in enumerate(detected_tables):
                    raw_bbox = getattr(table, "bbox", None)
                    normalized_bbox = _normalize_bbox(raw_bbox, page_width, page_height)
                    if normalized_bbox is None:
                        fallback_reasons.append("invalid_bbox")
                        continue

                    try:
                        crop_pix = page.get_pixmap(dpi=DEFAULT_PDF_RENDER_DPI, clip=normalized_bbox)
                        metadata = {
                            "page_number": page_number,
                            "file_name": normalized_name,
                            "asset_type": "table_crop",
                            "table_index_on_page": table_index,
                            "table_count_on_page": len(detected_tables),
                            "continued_from_previous_page": False,
                            "continued_to_next_page": False,
                            "_bbox": normalized_bbox,
                            "_page_width": page_width,
                            "_page_height": page_height,
                        }
                        assets.append(
                            ParsedPdfVisualAsset(
                                image_bytes=crop_pix.tobytes("png"),
                                page_number=page_number,
                                asset_type="table_crop",
                                metadata=metadata,
                            )
                        )
                    except Exception:
                        fallback_reasons.append("crop_render_failed")
                        continue

                    fallback_reason = _table_fallback_reason(
                        page=page,
                        bbox=normalized_bbox,
                        table_count=len(detected_tables),
                        page_width=page_width,
                        page_height=page_height,
                    )
                    if fallback_reason:
                        fallback_reasons.append(fallback_reason)

                if fallback_reasons:
                    page_pix = page.get_pixmap(dpi=DEFAULT_PDF_RENDER_DPI)
                    unique_reasons = list(dict.fromkeys(fallback_reasons))
                    assets.append(
                        ParsedPdfVisualAsset(
                            image_bytes=page_pix.tobytes("png"),
                            page_number=page_number,
                            asset_type="table_page_render",
                            metadata={
                                "page_number": page_number,
                                "file_name": normalized_name,
                                "asset_type": "table_page_render",
                                "table_count": len(detected_tables),
                                "fallback_reason": unique_reasons[0],
                                "related_table_indices": list(range(len(detected_tables))),
                            },
                        )
                    )
        except Exception:
            pass

    _group_cross_page_table_assets(assets, normalized_name)
    doc.close()
    return assets


def parse_pdf(
    file_bytes: bytes,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> Tuple[List[str], List[bytes]]:
    """兼容旧接口：返回文本片段列表和图片字节列表。"""
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name

        documents = extract_pdf_text_documents(tmp_path)
        text_chunks = [
            chunk.content
            for chunk in build_pdf_text_chunks(
                documents,
                doc_id="legacy-doc",
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        ]
        image_bytes_list = [asset.image_bytes for asset in extract_pdf_visual_assets(file_bytes)]
        return text_chunks, image_bytes_list
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
