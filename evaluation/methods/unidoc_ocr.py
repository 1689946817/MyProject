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

_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)

_OCR_SCRIPT = """
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
    except Exception:
        results[p] = ""
print(json.dumps(results, ensure_ascii=False))
"""


def _run_ocr_subprocess(image_paths: list[str]) -> dict[str, str]:
    paddle_python = os.environ.get("PADDLEOCR_PYTHON") or sys.executable
    proc = subprocess.run(
        [paddle_python, "-c", _OCR_SCRIPT, json.dumps(image_paths)],
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
    return col.count() > 0
