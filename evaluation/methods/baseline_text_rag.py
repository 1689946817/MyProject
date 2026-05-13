"""
Baseline A：仅文本检索（纯文本 RAG 系统）。

使用 COCO caption 或人工文本描述作为图像的文本表示，
通过 Embedding 模型向量化后存入 ChromaDB，检索时基于文本相似度匹配。

该基线假定已在 ChromaDB 中构建了名为 `images_text_only` 的集合，
集合中每条记录的 id 与评估数据集的 ground truth image ID 对齐。

与 Proposed 方法的区别：
- Baseline Text：使用原始 COCO caption（简短的自然语言描述）
- Proposed：使用 MLLM 生成的结构化长描述（包含更多视觉细节）

预期 Proposed 方法效果优于本基线，证明 MLLM 描述的质量优势。
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

# 初始化持久化 ChromaDB 客户端，使用与后端相同的存储目录
_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)
# Text baseline 使用独立集合，存放 COCO caption 文本向量
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

