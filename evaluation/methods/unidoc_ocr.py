"""
UniDoc-Bench Baseline OCR：OCR 文本向量检索。

集合命名：unidoc_{domain}_ocr
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

_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)

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
    return f"unidoc_{domain}_ocr"


def build_index(domain: str, image_records: List[dict], fallback_text: str = "[no text]") -> None:
    """构建 OCR 文本向量索引。"""
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
    embedder = get_embedding_model()
    emb = embedder.embed_query(query)
    col = _client.get_or_create_collection(name=_collection_name(domain))
    results = col.query(query_embeddings=[emb], n_results=top_k)
    return [str(i) for i in results.get("ids", [[]])[0]]


def check_index(domain: str) -> bool:
    col = _client.get_or_create_collection(name=_collection_name(domain))
    if col.count() == 0:
        return False

    sample = col.peek(limit=10)
    documents = sample.get("documents") or []
    return is_ocr_index_healthy(documents, fallback_text="[no text]")
