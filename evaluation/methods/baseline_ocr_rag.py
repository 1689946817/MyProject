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

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

# 将 backend 加入路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import settings  # noqa: E402
from app.langchain_integration.models import get_embedding_model  # noqa: E402
from evaluation.methods._ocr_common import (  # noqa: E402
    assert_ocr_stats_healthy,
    collect_ocr_stats,
    decode_ocr_subprocess_output,
    is_ocr_index_healthy,
    validate_ocr_python,
)

# 初始化 ChromaDB 客户端和集合
_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)
_collection_name = "images_ocr_text"
def _run_ocr_subprocess(image_paths: list[str]) -> dict[str, str]:
    """
    在独立子进程中批量执行 OCR，返回 {image_path: ocr_text} 映射。

    PaddleOCR 3.4.0 在 import 时初始化 PDX，同一进程不能重复初始化，
    因此将 OCR 隔离到子进程中运行。
    """
    # 内联子进程脚本
    script = """
import json, os, sys, types
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
def _install_langchain_compat():
    try:
        import langchain as _langchain
        from langchain_core.documents import Document as _Document
        from langchain_text_splitters import RecursiveCharacterTextSplitter as _TextSplitter

        _docstore_pkg = types.ModuleType("langchain.docstore")
        _doc_mod = types.ModuleType("langchain.docstore.document")
        _splitter_mod = types.ModuleType("langchain.text_splitter")
        _doc_mod.Document = _Document
        _splitter_mod.RecursiveCharacterTextSplitter = _TextSplitter
        _docstore_pkg.document = _doc_mod
        sys.modules["langchain.docstore"] = _docstore_pkg
        sys.modules["langchain.docstore.document"] = _doc_mod
        sys.modules["langchain.text_splitter"] = _splitter_mod
        setattr(_langchain, "docstore", _docstore_pkg)
        setattr(_langchain, "text_splitter", _splitter_mod)
    except Exception:
        pass

def _run_paddle(paths):
    _install_langchain_compat()
    from paddleocr import PaddleOCR

    print(f"[INFO] OCR engine used: PaddleOCR batch_size={len(paths)}", file=sys.stderr)
    ocr = PaddleOCR(use_textline_orientation=True, lang="en")
    results = {}
    for p in paths:
        pred = ocr.predict(p)
        lines = []
        for item in pred or []:
            rec_texts = getattr(item, "rec_texts", None)
            if rec_texts:
                lines.extend(str(t).strip() for t in rec_texts if str(t).strip())
        results[p] = " ".join(lines).strip()
    return results

def _run_rapid(paths):
    from rapidocr_onnxruntime import RapidOCR

    print(f"[INFO] OCR engine used: RapidOCR batch_size={len(paths)}", file=sys.stderr)
    engine = RapidOCR()
    results = {}
    for p in paths:
        try:
            pred, _ = engine(p)
            lines = [str(item[1]).strip() for item in (pred or []) if len(item) > 1 and str(item[1]).strip()]
            results[p] = " ".join(lines).strip()
        except Exception:
            results[p] = ""
    return results

paths = json.loads(sys.argv[1])
try:
    results = _run_paddle(paths)
except Exception as exc:
    print(f"[WARN] PaddleOCR failed, fallback to RapidOCR: {exc}", file=sys.stderr)
    results = _run_rapid(paths)
print(json.dumps(results, ensure_ascii=True))
"""
    paddle_python = os.environ.get("PADDLEOCR_PYTHON") or sys.executable
    validate_ocr_python(paddle_python)
    proc = subprocess.run(
        [paddle_python, "-c", script, json.dumps(image_paths)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr_text = (proc.stderr or "").strip()
    if stderr_text:
        for line in stderr_text.splitlines():
            if "OCR engine used" in line or "fallback to RapidOCR" in line:
                print(line)
    results = decode_ocr_subprocess_output(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
    return {p: results.get(p, "") for p in image_paths}


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
    collection = _client.get_or_create_collection(name=_collection_name)
    results = collection.query(query_embeddings=[emb], n_results=top_k)
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
    stats = collect_ocr_stats(ocr_results, fallback_text=fallback_text)
    print(
        "OCR stats:",
        f"total={stats['total_count']}",
        f"non_empty={stats['non_empty_raw_count']}",
        f"fallback={stats['fallback_count']}",
        f"unique={stats['unique_final_text_count']}",
    )
    assert_ocr_stats_healthy(stats, context=_collection_name)

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
    collection = _client.get_or_create_collection(name=_collection_name)
    if collection.count() == 0:
        return False

    sample = collection.peek(limit=10)
    documents = sample.get("documents") or []
    return is_ocr_index_healthy(documents, fallback_text="[no text]")
