"""
PDF 文档解析工具

从 PDF 文件中提取：
- 文本片段（语义分块：按句子边界切分后合并）
- 嵌入图片字节
- 含表格的页面整页渲染为 PNG 图片字节
"""
import re
from typing import List, Tuple

import fitz  # PyMuPDF


DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100

# 中英文句子结束符
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[。！？.!?\n])\s*')


def _sentence_aware_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    按句子边界切分文本，合并至 chunk_size 以内。
    保证不在句子中间截断，提升检索语义完整性。
    """
    if not text.strip():
        return []

    # 按句子边界拆分
    sentences = _SENTENCE_SPLIT_RE.split(text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return []

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for sent in sentences:
        sent_len = len(sent)

        # 单句超过 chunk_size，直接作为独立 chunk
        if sent_len > chunk_size:
            if current_chunk:
                chunks.append("".join(current_chunk))
                current_chunk = []
                current_len = 0
            chunks.append(sent)
            continue

        if current_len + sent_len > chunk_size and current_chunk:
            chunks.append("".join(current_chunk))
            # overlap: 保留最后几个句子作为下一个 chunk 的开头
            overlap_chunk: List[str] = []
            overlap_len = 0
            for s in reversed(current_chunk):
                if overlap_len + len(s) > overlap:
                    break
                overlap_chunk.insert(0, s)
                overlap_len += len(s)
            current_chunk = overlap_chunk
            current_len = overlap_len

        current_chunk.append(sent)
        current_len += sent_len

    if current_chunk:
        chunks.append("".join(current_chunk))

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
        # --- 文本提取与分块（语义分块） ---
        page_text = page.get_text("text")
        chunks = _sentence_aware_chunks(page_text, chunk_size, chunk_overlap)
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
