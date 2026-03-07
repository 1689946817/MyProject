"""
Baseline A：仅文本检索（纯文本 RAG 系统）。

在理想情况下，该基线应基于 COCO caption 或人工文本描述构建一个
独立的文本向量索引集合，这里假定你已经在 Chroma 中为该基线
构建了名为 `images_text_only` 的 collection，并将 id 与 ground truth 对齐。
"""

from __future__ import annotations

from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.app.core.config import settings
from backend.app.retrieval.embedding_client import get_embedding_client


_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)
_collection = _client.get_or_create_collection(name="images_text_only")


def retrieve(query: str, top_k: int = 10) -> List[str]:
    """
    基于文本查询 text-only 向量集合，返回预测的图像 ID 列表。
    """
    embedder = get_embedding_client()
    emb = embedder.embed_texts([query])[0]
    results: Dict[str, Any] = _collection.query(query_embeddings=[emb], n_results=top_k)
    ids = results.get("ids", [[]])[0]
    return [str(i) for i in ids]

