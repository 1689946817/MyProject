from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.retrieval.embedding_client import get_embedding_client


_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)

_collection = _client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME)


def upsert_image_description(doc_id: str, text: str, metadata: Dict[str, Any]) -> None:
    """
    将图像的结构化文本描述写入向量库。
    """
    embedder = get_embedding_client()
    embeddings = embedder.embed_texts([text])
    _collection.upsert(
        ids=[doc_id],
        documents=[text],
        embeddings=embeddings,
        metadatas=[metadata],
    )


def search_by_text(query_text: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    基于文本查询向量库，返回带相似度分数的结果列表。
    """
    embedder = get_embedding_client()
    query_embedding = embedder.embed_texts([query_text])[0]
    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    hits: List[Dict[str, Any]] = []
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc_id, doc, meta, dist in zip(ids, docs, metadatas, distances):
        hits.append(
            {
                "id": doc_id,
                "document": doc,
                "metadata": meta,
                "score": float(dist),
            }
        )

    return hits

