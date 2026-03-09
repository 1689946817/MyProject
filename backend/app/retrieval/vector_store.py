"""
向量存储模块

该模块负责管理 ChromaDB 向量存储，包括：
- 初始化 ChromaDB 客户端和集合
- 将图像描述写入向量库
- 基于文本查询向量库

是实现文本检索和图像检索的核心组件。
"""
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.retrieval.embedding_client import get_embedding_client


# 初始化 ChromaDB 客户端
# 配置为持久化存储，存储目录从配置文件获取
_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)

# 获取或创建向量存储集合
# 集合名称从配置文件获取，用于存储图像的语义描述
_collection = _client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME)


def upsert_image_description(doc_id: str, text: str, metadata: Dict[str, Any]) -> None:
    """将图像描述写入向量库
    
    将图像的结构化文本描述生成嵌入向量并写入 ChromaDB 向量库。
    如果文档已存在，则更新其内容。
    
    Args:
        doc_id: 文档唯一标识符（与图像 ID 对应）
        text: 图像的结构化文本描述
        metadata: 文档元数据，包含文件路径等信息
    """
    # 获取嵌入模型客户端
    embedder = get_embedding_client()
    # 生成文本的向量嵌入
    embeddings = embedder.embed_texts([text])
    # 写入或更新向量库
    _collection.upsert(
        ids=[doc_id],
        documents=[text],
        embeddings=embeddings,
        metadatas=[metadata],
    )


def search_by_text(query_text: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """基于文本查询向量库
    
    将查询文本生成嵌入向量，然后在向量库中查找最相似的文档。
    
    Args:
        query_text: 查询文本
        top_k: 返回的结果数量，默认为 10
    
    Returns:
        List[Dict[str, Any]]: 包含相似度分数的结果列表，每个结果包含 id、document、metadata 和 score
    """
    # 获取嵌入模型客户端
    embedder = get_embedding_client()
    # 生成查询文本的向量嵌入
    query_embedding = embedder.embed_texts([query_text])[0]
    # 在向量库中查询相似文档
    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    # 处理查询结果
    hits: List[Dict[str, Any]] = []
    # 从结果中提取数据
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    # 构建结果列表，包含 id、文档内容、元数据和相似度分数
    for doc_id, doc, meta, dist in zip(ids, docs, metadatas, distances):
        hits.append(
            {
                "id": doc_id,
                "document": doc,
                "metadata": meta,
                "score": float(dist),  # 距离值，值越小相似度越高
            }
        )

    return hits

