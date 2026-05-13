"""
UniDoc-Bench Baseline OCR：OCR 文本向量检索。

对每张图像执行 OCR 文字识别，将识别出的文本通过 Embedding 模型向量化后
存入 ChromaDB 集合（命名规则：unidoc_{domain}_ocr），
检索时将查询文本 Embedding，在向量库中执行余弦相似度检索。

OCR 引擎策略（子进程隔离执行）：
  - 主引擎：PaddleOCR（精度更高）
  - 备用引擎：RapidOCR（无需 PaddlePaddle 环境）
  - 通过 PADDLEOCR_PYTHON 环境变量指定专用 Python 解释器

集合命名规则：unidoc_{domain}_ocr
例如：unidoc_clip_ocr、unidoc_healthcare_ocr
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List

import chromadb
from chromadb.config import Settings as ChromaSettings

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

# 初始化持久化 ChromaDB 客户端
_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)

# OCR 子进程内联脚本：通过 stdin 接收图片路径 JSON，stdout 输出识别结果 JSON
# 优先使用 PaddleOCR，失败时自动降级到 RapidOCR
_OCR_SCRIPT = """
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

paths = json.loads(sys.stdin.read())
try:
    results = _run_paddle(paths)
except Exception as exc:
    print(f"[WARN] PaddleOCR failed, fallback to RapidOCR: {exc}", file=sys.stderr)
    results = _run_rapid(paths)
print(json.dumps(results, ensure_ascii=True))
"""


def _run_ocr_subprocess(image_paths: list[str]) -> dict[str, str]:
    """在独立子进程中批量执行 OCR 识别。

    子进程通过 stdin 接收图片路径列表的 JSON，stdout 输出 {path: text} JSON。
    使用 PADDLEOCR_PYTHON 环境变量指定的 Python 解释器运行。

    Args:
        image_paths: 待识别的图像文件路径列表。

    Returns:
        dict[str, str]: {图像路径: OCR 识别文本} 映射。
    """
    paddle_python = os.environ.get("PADDLEOCR_PYTHON") or sys.executable
    validate_ocr_python(paddle_python)
    proc = subprocess.run(
        [paddle_python, "-c", _OCR_SCRIPT],
        input=json.dumps(image_paths),
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


def _collection_name(domain: str) -> str:
    """生成 ChromaDB 集合名称，命名规则：unidoc_{domain}_ocr。"""
    return f"unidoc_{domain}_ocr"


def build_index(domain: str, image_records: List[dict], fallback_text: str = "[no text]") -> None:
    """构建 OCR 文本向量索引。

    对每张图像执行 OCR（子进程隔离），将提取的文字通过 Embedding 模型
    向量化后存入 ChromaDB 集合 unidoc_{domain}_ocr。

    健康性检查：调用 _ocr_common 的统计函数验证 OCR 结果是否有效，
    避免将全空或全相同的异常索引提交到 ChromaDB。

    Args:
        domain: 领域名称，影响集合命名和元数据。
        image_records: 图像记录列表，每条需包含 id 和 file_path。
        fallback_text: OCR 结果为空时的替代文本，默认 "[no text]"。
    """
    embedder = get_embedding_model()

    valid_records = [r for r in image_records if os.path.exists(r["file_path"])]
    skipped = len(image_records) - len(valid_records)
    if skipped:
        print(f"[SKIP] {skipped} images not found on disk.")
    if not valid_records:
        print("[WARNING] No valid images to process.")
        return

    print(f"Running OCR on {len(valid_records)} images (subprocess)...")
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
    assert_ocr_stats_healthy(stats, context=f"unidoc_{domain}_ocr")

    ids = []
    texts = []
    metadatas = []
    for record in valid_records:
        file_path = record["file_path"]
        ocr_text = ocr_results.get(file_path, "") or fallback_text
        # 文档页面 OCR 文本可能很长，截断到 500 字符
        ocr_text_stored = ocr_text[:500]
        ids.append(record["id"])
        texts.append(ocr_text)
        metadatas.append({
            "file_path": file_path,
            "domain": domain,
            "ocr_text": ocr_text_stored,
            "source": "unidoc_ocr",
        })

    print(f"Embedding {len(texts)} OCR texts...")
    embeddings = embedder.embed_documents(texts)

    col_name = _collection_name(domain)
    try:
        _client.delete_collection(col_name)
    except Exception:
        pass
    col = _client.get_or_create_collection(name=col_name)
    col.add(embeddings=embeddings, documents=texts, ids=ids, metadatas=metadatas)
    print(f"Index built: {len(ids)} images in '{col_name}'")


def retrieve(query: str, domain: str, top_k: int = 10) -> List[str]:
    """使用 OCR 方法检索图像。

    检索路径：查询文本 → Embedding → ChromaDB 余弦相似度检索。

    Args:
        query: 查询文本。
        domain: 领域名称，决定检索哪个集合。
        top_k: 返回的检索结果数量，默认 10。

    Returns:
        List[str]: top_k 个预测图像 ID 列表。
    """
    embedder = get_embedding_model()
    emb = embedder.embed_query(query)
    col = _client.get_or_create_collection(name=_collection_name(domain))
    results = col.query(query_embeddings=[emb], n_results=top_k)
    return [str(i) for i in results.get("ids", [[]])[0]]


def check_index(domain: str) -> bool:
    """检查指定领域的 OCR 索引是否已构建且健康。

    抽样 10 条文档检查：非空、不全为 fallback、不完全相同。

    Args:
        domain: 领域名称。

    Returns:
        bool: True 表示索引健康。
    """
    col = _client.get_or_create_collection(name=_collection_name(domain))
    if col.count() == 0:
        return False

    # 抽样检查索引内容质量
    sample = col.peek(limit=10)
    documents = sample.get("documents") or []
    return is_ocr_index_healthy(documents, fallback_text="[no text]")
