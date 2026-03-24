"""
UniDoc-Bench Proposed 方法：MLLM 描述 + 文本向量检索。

集合命名：unidoc_{domain}_proposed
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
import time
from pathlib import Path
from typing import List

import chromadb
from chromadb.config import Settings as ChromaSettings

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import settings  # noqa: E402
from app.langchain_integration.chains import get_image_description_chain  # noqa: E402
from app.langchain_integration.models import get_embedding_model, guess_image_mime_type  # noqa: E402

_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)


def _collection_name(domain: str) -> str:
    return f"unidoc_{domain}_proposed"


def _generate_description_with_retry(
    chain,
    file_path: str,
    max_retries: int = 3,
    base_backoff_seconds: float = 2.0,
) -> tuple[str, str | None]:
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    mime_type = guess_image_mime_type(file_path)

    last_error: str | None = None
    total_attempts = max_retries + 1
    for attempt in range(1, total_attempts + 1):
        try:
            desc = asyncio.run(chain.ainvoke({"image_b64": b64, "mime_type": mime_type}))
            if attempt > 1:
                print(f"[INFO] Retry succeeded for {file_path} on attempt {attempt}/{total_attempts}")
            return desc, None
        except Exception as e:
            error_message = str(e).strip() or repr(e)
            last_error = error_message
            print(
                f"[WARN] MLLM failed for {file_path} "
                f"(attempt {attempt}/{total_attempts}): {error_message}"
            )
            if attempt < total_attempts:
                sleep_seconds = base_backoff_seconds * (2 ** (attempt - 1))
                print(f"[INFO] Backing off for {sleep_seconds:.1f}s before retrying {file_path}")
                time.sleep(sleep_seconds)

    return "[no description]", last_error


def build_index(domain: str, image_records: List[dict]) -> None:
    """构建 MLLM 描述向量索引。"""
    chain = get_image_description_chain()
    embedder = get_embedding_model()

    valid_records = [r for r in image_records if os.path.exists(r["file_path"])]
    skipped = len(image_records) - len(valid_records)
    if skipped:
        print(f"[SKIP] {skipped} images not found on disk.")
    if not valid_records:
        print("[WARNING] No valid images to process.")
        return

    ids = []
    descriptions = []
    metadatas = []
    failed_files: List[tuple[str, str]] = []

    print(f"Generating MLLM descriptions for {len(valid_records)} images...")
    for i, record in enumerate(valid_records):
        file_path = record["file_path"]
        desc, error_message = _generate_description_with_retry(chain, file_path)
        if error_message is not None:
            failed_files.append((file_path, error_message))

        ids.append(record["id"])
        descriptions.append(desc)
        metadatas.append({"file_path": file_path, "domain": domain, "source": "unidoc_proposed"})

        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(valid_records)} done")
            time.sleep(2)

    print(f"Embedding {len(descriptions)} descriptions...")
    embeddings = embedder.embed_documents(descriptions)

    success_count = len(valid_records) - len(failed_files)
    print(
        f"Description generation summary: {success_count}/{len(valid_records)} succeeded, "
        f"{len(failed_files)} failed"
    )
    if failed_files:
        print("Failed files:")
        for file_path, error_message in failed_files:
            print(f"  - {file_path}: {error_message}")

    col_name = _collection_name(domain)
    try:
        _client.delete_collection(col_name)
    except Exception:
        pass
    col = _client.get_or_create_collection(name=col_name)
    col.add(embeddings=embeddings, documents=descriptions, ids=ids, metadatas=metadatas)
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
