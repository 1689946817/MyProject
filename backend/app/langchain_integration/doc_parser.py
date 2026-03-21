"""
PDF 文档解析工具

从 PDF 文件中提取：
- 文本片段（滑动窗口分块）
- 嵌入图片字节
- 含表格的页面整页渲染为 PNG 图片字节
"""
from typing import List, Tuple

import fitz  # PyMuPDF


DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100


def _sliding_window_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """将文本按滑动窗口分块。"""
    if not text.strip():
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += chunk_size - overlap
    return chunks


def parse_pdf(
    file_bytes: bytes,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> Tuple[List[str], List[bytes]]:
    """
    解析 PDF，返回文本片段列表和图片字节列表。

    图片来源：
    1. 每页嵌入的图片（page.get_images）
    2. 含表格的页面整页渲染为 PNG（dpi=150）

    Args:
        file_bytes: PDF 文件的原始字节
        chunk_size: 文本分块大小（字符数）
        chunk_overlap: 分块重叠大小（字符数）

    Returns:
        (text_chunks, image_bytes_list)
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    text_chunks: List[str] = []
    image_bytes_list: List[bytes] = []
    seen_xrefs: set = set()  # 避免重复提取同一张嵌入图片

    for page in doc:
        # --- 文本提取与分块 ---
        page_text = page.get_text("text")
        chunks = _sliding_window_chunks(page_text, chunk_size, chunk_overlap)
        text_chunks.extend(chunks)

        # --- 嵌入图片提取 ---
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                if img_bytes:
                    image_bytes_list.append(img_bytes)
            except Exception:
                pass

        # --- 含表格页面整页渲染 ---
        try:
            tables = page.find_tables()
            if tables and len(tables.tables) > 0:
                pix = page.get_pixmap(dpi=150)
                image_bytes_list.append(pix.tobytes("png"))
        except Exception:
            pass

    doc.close()
    return text_chunks, image_bytes_list
