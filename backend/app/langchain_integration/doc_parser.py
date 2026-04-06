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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple, Type

import fitz  # PyMuPDF
from langchain_core.documents import Document

from app.core.config import settings


DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100

# 中英文句子结束符
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?\n])\s*")


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


def extract_pdf_visual_assets(
    file_bytes: bytes,
    file_name: str | None = None,
) -> List[ParsedPdfVisualAsset]:
    """提取 PDF 嵌入图片和含表格页面的整页渲染结果。"""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    assets: List[ParsedPdfVisualAsset] = []
    seen_xrefs: set[int] = set()
    normalized_name = file_name or "document.pdf"

    for page_index, page in enumerate(doc):
        page_number = page_index + 1

        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                if img_bytes:
                    assets.append(
                        ParsedPdfVisualAsset(
                            image_bytes=img_bytes,
                            page_number=page_number,
                            asset_type="embedded_image",
                            metadata={
                                "page_number": page_number,
                                "file_name": normalized_name,
                                "asset_type": "embedded_image",
                            },
                        )
                    )
            except Exception:
                pass

        try:
            tables = page.find_tables()
            if tables and len(tables.tables) > 0:
                pix = page.get_pixmap(dpi=150)
                assets.append(
                    ParsedPdfVisualAsset(
                        image_bytes=pix.tobytes("png"),
                        page_number=page_number,
                        asset_type="table_page_render",
                        metadata={
                            "page_number": page_number,
                            "file_name": normalized_name,
                            "asset_type": "table_page_render",
                            "table_count": len(tables.tables),
                        },
                    )
                )
        except Exception:
            pass

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
