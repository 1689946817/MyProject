"""
LangChain 向量存储集成模块

该模块提供基于 LangChain 的向量存储实现，包括：
- ChromaDB 向量存储封装
- 文档添加、查询、删除等操作
- 与 LangChain Retriever 接口的兼容

使用 LangChain 的标准接口封装现有的 ChromaDB 存储，实现与 LangChain 生态的无缝集成。
"""
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_community.vectorstores import Chroma

from app.core.config import settings
from app.langchain_integration.models import get_embedding_model


class ChromaVectorStore:
    """
    ChromaDB 向量存储封装类

    基于 LangChain Chroma 实现的向量存储封装，提供：
    - 文档的添加、更新、删除
    - 相似度搜索
    - 与现有 ChromaDB 集合的兼容

    保持与现有数据存储的兼容性，同时提供 LangChain 标准接口。
    """

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        """
        初始化向量存储

        Args:
            persist_directory: 持久化目录，默认从配置读取
            collection_name: 集合名称，默认从配置读取
        """
        self.persist_directory = persist_directory or settings.CHROMA_PERSIST_DIR
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME
        self.embedding_model = get_embedding_model()

        # 初始化 LangChain Chroma 向量存储
        self._vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embedding_model,
            persist_directory=self.persist_directory,
        )

    def add_documents(
        self,
        documents: List[Document],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        添加文档到向量存储

        Args:
            documents: 文档列表
            ids: 文档 ID 列表，可选

        Returns:
            List[str]: 添加的文档 ID 列表
        """
        return self._vectorstore.add_documents(documents, ids=ids)

    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        添加文本到向量存储

        Args:
            texts: 文本列表
            metadatas: 元数据列表，可选
            ids: 文档 ID 列表，可选

        Returns:
            List[str]: 添加的文档 ID 列表
        """
        return self._vectorstore.add_texts(texts, metadatas=metadatas, ids=ids)

    def similarity_search(
        self,
        query: str,
        k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        相似度搜索

        Args:
            query: 查询文本
            k: 返回结果数量
            filter: 元数据过滤条件

        Returns:
            List[Document]: 相似文档列表
        """
        return self._vectorstore.similarity_search(query, k=k, filter=filter)

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """
        带分数的相似度搜索

        Args:
            query: 查询文本
            k: 返回结果数量
            filter: 元数据过滤条件

        Returns:
            List[Tuple[Document, float]]: (文档, 相似度分数) 列表
        """
        return self._vectorstore.similarity_search_with_score(query, k=k, filter=filter)

    def delete(self, ids: Optional[List[str]] = None) -> Optional[bool]:
        """
        删除文档

        Args:
            ids: 要删除的文档 ID 列表

        Returns:
            Optional[bool]: 是否成功
        """
        return self._vectorstore.delete(ids=ids)

    def get_by_ids(self, ids: List[str]) -> List[Document]:
        """
        根据 ID 获取文档

        Args:
            ids: 文档 ID 列表

        Returns:
            List[Document]: 文档列表
        """
        return self._vectorstore.get_by_ids(ids)

    def upsert_image_description(
        self,
        doc_id: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> None:
        """
        更新或插入图像描述（兼容现有接口）

        Args:
            doc_id: 文档 ID
            text: 图像描述文本
            metadata: 元数据
        """
        # 先删除已存在的文档
        self.delete(ids=[doc_id])
        # 添加新文档
        self.add_texts([text], metadatas=[metadata], ids=[doc_id])

    def search_by_text(
        self,
        query_text: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        基于文本搜索（兼容现有接口）

        Args:
            query_text: 查询文本
            top_k: 返回结果数量

        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        results = self.similarity_search_with_score(query_text, k=top_k)

        hits = []
        for doc, score in results:
            hits.append({
                "id": doc.metadata.get("id", ""),
                "document": doc.page_content,
                "metadata": doc.metadata,
                "score": float(score),
            })

        return hits

    def as_retriever(self, search_kwargs: Optional[Dict[str, Any]] = None):
        """
        获取 LangChain Retriever 接口

        Args:
            search_kwargs: 搜索参数

        Returns:
            BaseRetriever: LangChain 检索器
        """
        return self._vectorstore.as_retriever(search_kwargs=search_kwargs or {"k": 10})

    @property
    def vectorstore(self) -> Chroma:
        """获取底层 Chroma 实例"""
        return self._vectorstore


# 全局向量存储实例缓存
_vector_store: Optional[ChromaVectorStore] = None


def get_vector_store() -> ChromaVectorStore:
    """
    获取向量存储实例（单例模式）

    Returns:
        ChromaVectorStore: 向量存储实例
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = ChromaVectorStore()
    return _vector_store
