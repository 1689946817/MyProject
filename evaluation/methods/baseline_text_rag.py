"""
Baseline A：仅文本检索（纯文本 RAG 系统）。

在理想情况下，该基线应基于 COCO caption 或人工文本描述构建一个
独立的文本向量索引集合，这里假定你已经在 Chroma 中为该基线
构建了名为 `images_text_only` 的 collection，并将 id 与 ground truth 对齐。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings as ChromaSettings

# 将 backend 加入路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import settings  # noqa: E402
from app.langchain_integration.models import get_embedding_model  # noqa: E402


_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)
_collection = _client.get_or_create_collection(name="images_text_only")


def build_text_index(image_records: List[dict]) -> None:
    """
    构建纯文本向量索引。

    将 COCO caption 或人工文本描述向量化后存入 ChromaDB。
    需要在运行评估前调用此函数构建向量库。

    Args:
        image_records: 图像记录列表，每个记录应包含：
            - id: 图像 ID（字符串）
            - caption: COCO caption 或人工描述文本
            - file_path: 图像文件路径（可选，用于元数据）
    """
    embedder = get_embedding_model()

    ids = [record["id"] for record in image_records]
    texts = [record["caption"] for record in image_records]
    metadatas = [
        {"file_path": record.get("file_path", ""), "source": "baseline_text"}
        for record in image_records
    ]

    print(f"Embedding {len(texts)} captions...")
    embeddings = embedder.embed_documents(texts)

    existing = _collection.count()
    if existing > 0:
        _collection.delete(where=None)  # 删除所有文档

    _collection.add(
        embeddings=embeddings,
        documents=texts,
        ids=ids,
        metadatas=metadatas,
    )
    print(f"Text index built: {len(ids)} records in collection 'images_text_only'")


def check_text_index() -> bool:
    """检查文本向量索引是否已构建。"""
    return _collection.count() > 0


def retrieve(query: str, top_k: int = 10) -> List[str]:
    """
    基于文本查询 text-only 向量集合，返回预测的图像 ID 列表。
    """
    embedder = get_embedding_model()
    emb = embedder.embed_query(query)
    results: Dict[str, Any] = _collection.query(query_embeddings=[emb], n_results=top_k)
    ids = results.get("ids", [[]])[0]
    return [str(i) for i in ids]

