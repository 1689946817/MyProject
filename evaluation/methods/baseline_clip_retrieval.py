"""
Baseline B：跨模态嵌入（qwen3-vl-embedding）检索。

使用 qwen3-vl-embedding 多模态融合向量模型，支持：
- 文本→图像检索（文本编码 + 图像向量库）
- 图像→图像检索（图像编码 + 图像向量库）

向量库使用独立的 ChromaDB 集合：`images_multimodal_embedding`
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

import chromadb
from chromadb.config import Settings as ChromaSettings

# 将 backend 加入路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import settings  # noqa: E402
from app.langchain_integration.models import get_multimodal_embedding_model  # noqa: E402

# 初始化 ChromaDB 客户端和集合
_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)
_collection_name = "images_multimodal_embedding"
_collection = _client.get_or_create_collection(name=_collection_name)


def retrieve_text(query: str, top_k: int = 10) -> List[str]:
    """
    文本→图像检索（qwen3-vl-embedding 文本编码 + 图像向量库）。

    使用 qwen3-vl-embedding 将查询文本编码为向量，
    在图像向量库中检索最相似的图像。

    Args:
        query: 查询文本
        top_k: 返回的 top-k 结果数量

    Returns:
        List[str]: top_k 个预测图像 ID 列表
    """
    embedder = get_multimodal_embedding_model()

    # 将查询文本编码为向量
    query_embedding = embedder.embed_query(query)

    # 在向量库中检索
    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )

    ids = results.get("ids", [[]])[0]
    return [str(i) for i in ids]


def retrieve_image(image_path: str, top_k: int = 10) -> List[str]:
    """
    图像→图像检索（qwen3-vl-embedding 图像编码 + 图像向量库）。

    使用 qwen3-vl-embedding 将查询图像编码为向量，
    在图像向量库中检索最相似的图像。

    Args:
        image_path: 查询图像文件路径
        top_k: 返回的 top-k 结果数量

    Returns:
        List[str]: top_k 个预测图像 ID 列表
    """
    embedder = get_multimodal_embedding_model()

    # 检查是否支持图像嵌入
    if not hasattr(embedder, 'embed_images'):
        raise NotImplementedError(
            "Current embedding client does not support image embedding. "
            "Please use DashScopeEmbeddingClient with qwen3-vl-embedding model."
        )

    # 检查图像文件是否存在
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # 将查询图像编码为向量
    image_embedding = embedder.embed_images([image_path])[0]

    # 在向量库中检索
    results = _collection.query(
        query_embeddings=[image_embedding],
        n_results=top_k
    )

    ids = results.get("ids", [[]])[0]
    return [str(i) for i in ids]


def retrieve(query: str, top_k: int = 10) -> List[str]:
    """
    统一的检索接口，用于离线评估。

    对于 Baseline CLIP Retrieval，我们只评估文本→图像检索性能，
    因此这里调用 retrieve_text 方法。

    Args:
        query: 查询文本
        top_k: 返回的 top-k 结果数量

    Returns:
        List[str]: top_k 个预测图像 ID 列表
    """
    return retrieve_text(query, top_k)


def build_vector_index(image_records: List[dict]) -> None:
    """
    构建图像向量索引。

    将图像编码为向量并存入 ChromaDB 集合。
    需要在运行评估前调用此函数构建向量库。

    Args:
        image_records: 图像记录列表，每个记录应包含：
            - id: 图像 ID（字符串）
            - file_path: 图像文件路径
            - description: 图像描述（可选，用于元数据）
    """
    embedder = get_multimodal_embedding_model()

    # 检查是否支持图像嵌入
    if not hasattr(embedder, 'embed_images'):
        raise NotImplementedError(
            "Current embedding client does not support image embedding. "
            "Please use DashScopeEmbeddingClient with qwen3-vl-embedding model."
        )

    # 提取图像路径
    image_paths = [record["file_path"] for record in image_records]
    ids = [record["id"] for record in image_records]

    # 批量编码图像
    print(f"Encoding {len(image_paths)} images using qwen3-vl-embedding...")
    embeddings = embedder.embed_images(image_paths)

    # 准备元数据
    metadatas = []
    for record in image_records:
        metadata = {
            "file_path": record["file_path"],
            "description": record.get("description", ""),
            "source": "baseline_clip"
        }
        metadatas.append(metadata)

    # 清空现有集合并添加新数据
    _collection.delete(where={})  # 删除所有文档
    _collection.add(
        embeddings=embeddings,
        ids=ids,
        metadatas=metadatas
    )

    print(f"Successfully built vector index with {len(ids)} images in collection '{_collection_name}'")


def check_vector_index() -> bool:
    """
    检查向量索引是否已构建。

    Returns:
        bool: 向量索引是否包含数据
    """
    count = _collection.count()
    return count > 0