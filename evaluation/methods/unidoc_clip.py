"""
UniDoc-Bench Baseline CLIP：qwen3-vl-embedding 图像检索。

集合命名：unidoc_{domain}_clip
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

import chromadb
from chromadb.config import Settings as ChromaSettings

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import settings  # noqa: E402
from app.langchain_integration.models import get_multimodal_embedding_model  # noqa: E402

_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)


def _collection_name(domain: str) -> str:
    return f"unidoc_{domain}_clip"


def build_index(domain: str, image_records: List[dict]) -> None:
    """构建图像向量索引（qwen3-vl-embedding）。"""
    embedder = get_multimodal_embedding_model()
    if not hasattr(embedder, "embed_images"):
        raise NotImplementedError("Multimodal embedding model does not support embed_images.")

    valid_records = [r for r in image_records if os.path.exists(r["file_path"])]
    skipped = len(image_records) - len(valid_records)
    if skipped:
        print(f"[SKIP] {skipped} images not found on disk.")
    if not valid_records:
        print("[WARNING] No valid images to process.")
        return

    image_paths = [r["file_path"] for r in valid_records]
    ids = [r["id"] for r in valid_records]
    metadatas = [{"file_path": r["file_path"], "domain": domain, "source": "unidoc_clip"} for r in valid_records]

    print(f"Encoding {len(image_paths)} images with qwen3-vl-embedding...")
    embeddings = embedder.embed_images(image_paths)

    col_name = _collection_name(domain)
    try:
        _client.delete_collection(col_name)
    except Exception:
        pass
    col = _client.get_or_create_collection(name=col_name)
    col.add(embeddings=embeddings, ids=ids, metadatas=metadatas)
    print(f"Index built: {len(ids)} images in '{col_name}'")


def retrieve(query: str, domain: str, top_k: int = 10) -> List[str]:
    embedder = get_multimodal_embedding_model()
    emb = embedder.embed_query(query)
    col = _client.get_or_create_collection(name=_collection_name(domain))
    results = col.query(query_embeddings=[emb], n_results=top_k)
    return [str(i) for i in results.get("ids", [[]])[0]]


def check_index(domain: str) -> bool:
    col = _client.get_or_create_collection(name=_collection_name(domain))
    return col.count() > 0
