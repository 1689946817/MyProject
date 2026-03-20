"""
Baseline C：基于 OCR 与文档结构解析的多模态 RAG 流程。

核心思路：
  对图像进行 OCR 识别，提取图中实际存在的文字，将其向量化后存入
  独立的 ChromaDB 集合 `images_ocr_text`，检索时同样走文本向量检索。

局限性（预期效果差，用于衬托本项目方法的优势）：
  - MS-COCO 是自然场景图像，图中文字极少，OCR 提取内容非常有限
  - 对于无文字图像，OCR 结果为空，检索退化为随机
  - 无法理解图像语义内容，只能匹配字面文字

依赖：
  pip install paddlepaddle paddleocr
  或
  pip install pytesseract Pillow  （需额外安装 Tesseract 可执行文件）

向量库使用独立的 ChromaDB 集合：`images_ocr_text`
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

# 将 backend 加入路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import settings  # noqa: E402
from app.langchain_integration.models import get_embedding_model  # noqa: E402

# 初始化 ChromaDB 客户端和集合
_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)
_collection_name = "images_ocr_text"
_collection = _client.get_or_create_collection(name=_collection_name)


_paddle_ocr = None


def _run_ocr_subprocess(image_paths: list[str]) -> dict[str, str]:
    """
    在独立子进程中批量执行 OCR，返回 {image_path: ocr_text} 映射。

    PaddleOCR 3.4.0 在 import 时初始化 PDX，同一进程不能重复初始化，
    因此将 OCR 隔离到子进程中运行。
    """
    import json
    import subprocess
    import sys

    # 内联子进程脚本
    script = """
import sys, json
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
paths = json.loads(sys.argv[1])
results = {}
for p in paths:
    try:
        r = ocr.ocr(p, cls=True)
        if r and r[0]:
            lines = [w[1][0] for line in r for w in line if w]
            results[p] = " ".join(lines).strip()
        else:
            results[p] = ""
    except Exception as e:
        results[p] = ""
print(json.dumps(results, ensure_ascii=False))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, json.dumps(image_paths)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        print(f"[WARN] OCR subprocess error: {proc.stderr[:200]}")
        return {p: "" for p in image_paths}
    try:
        return json.loads(proc.stdout.strip())
    except Exception:
        return {p: "" for p in image_paths}


def _extract_text_ocr(image_path: str) -> str:
    """
    对单张图像执行 OCR，返回提取到的文字字符串。

    优先使用 PaddleOCR（中英文支持更好），若未安装则回退到 pytesseract。
    若两者均未安装，返回空字符串并打印警告。

    Args:
        image_path: 图像文件路径

    Returns:
        str: OCR 提取的文字，多行合并为空格分隔的单行；无文字时返回空字符串
    """
    # 优先尝试 PaddleOCR
    try:
        global _paddle_ocr
        from paddleocr import PaddleOCR
        if _paddle_ocr is None:
            _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        result = _paddle_ocr.ocr(image_path, cls=True)
        if not result or not result[0]:
            return ""
        lines = [word_info[1][0] for line in result for word_info in line if word_info]
        return " ".join(lines).strip()
    except ImportError:
        pass

    # 回退到 pytesseract
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang="eng")
        return " ".join(text.split())
    except ImportError:
        pass

    print(f"[WARNING] No OCR library found. Install paddleocr or pytesseract. Returning empty text for {image_path}")
    return ""


def retrieve(query: str, top_k: int = 10) -> List[str]:
    """
    基于文本查询 OCR 向量集合，返回预测的图像 ID 列表。

    Args:
        query: 查询文本
        top_k: 返回的 top-k 结果数量

    Returns:
        List[str]: top_k 个预测图像 ID 列表
    """
    embedder = get_embedding_model()
    emb = embedder.embed_query(query)
    results = _collection.query(query_embeddings=[emb], n_results=top_k)
    ids = results.get("ids", [[]])[0]
    return [str(i) for i in ids]


def build_ocr_index(image_records: List[dict], fallback_text: Optional[str] = None) -> None:
    """
    构建 OCR 文本向量索引。

    对每张图像执行 OCR，将提取的文字向量化后存入 ChromaDB。
    需要在运行评估前调用此函数构建向量库。

    Args:
        image_records: 图像记录列表，每个记录应包含：
            - id: 图像 ID（字符串）
            - file_path: 图像文件路径
        fallback_text: OCR 结果为空时的替代文本，默认为 "[no text]"
    """
    if fallback_text is None:
        fallback_text = "[no text]"

    embedder = get_embedding_model()

    # 过滤出存在的图片
    valid_records = [r for r in image_records if os.path.exists(r["file_path"])]
    skipped = len(image_records) - len(valid_records)
    if skipped:
        print(f"[SKIP] {skipped} images not found on disk.")

    if not valid_records:
        print("[WARNING] No valid images to process.")
        return

    # 用子进程批量跑 OCR，避免 PaddleOCR PDX 重复初始化问题
    print(f"Running OCR on {len(valid_records)} images (subprocess) ...")
    image_paths = [r["file_path"] for r in valid_records]
    ocr_results = _run_ocr_subprocess(image_paths)

    ids = []
    texts = []
    metadatas = []
    for record in valid_records:
        image_path = record["file_path"]
        ocr_text = ocr_results.get(image_path, "") or fallback_text
        ids.append(record["id"])
        texts.append(ocr_text)
        metadatas.append({
            "file_path": image_path,
            "ocr_text": ocr_text,
            "source": "baseline_ocr",
        })

    if not ids:
        print("[WARNING] No valid images processed, index is empty.")
        return

    print(f"Embedding {len(texts)} OCR texts...")
    embeddings = embedder.embed_documents(texts)

    # 删除旧集合并重建，避免 ChromaDB delete API 的版本兼容问题
    _client.delete_collection(_collection_name)
    fresh = _client.get_or_create_collection(name=_collection_name)
    fresh.add(
        embeddings=embeddings,
        documents=texts,
        ids=ids,
        metadatas=metadatas,
    )
    print(f"OCR index built: {len(ids)} images in collection '{_collection_name}'")


def check_ocr_index() -> bool:
    """检查 OCR 向量索引是否已构建。"""
    return _collection.count() > 0
