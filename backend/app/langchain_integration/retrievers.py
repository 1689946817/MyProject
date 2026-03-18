"""
LangChain 检索器集成模块

该模块提供基于 LangChain 的检索器实现，包括：
- 多模态检索器（支持文本和图像查询）
- 自定义检索逻辑封装
- 与 LangChain Chain 的集成
"""
import base64
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile
from langchain_core.documents import Document

from app.langchain_integration.models import get_chat_model, MultimodalChatModel
from app.langchain_integration.vectorstores import ChromaVectorStore, get_vector_store
from app.retrieval.rerank import simple_rerank
from app.semantic.prompts import IMAGE_DESCRIPTION_PROMPT



class MultimodalRetriever:
    """
    多模态检索器

    支持：
    - 文本到图像检索
    - 图像到图像检索（通过生成描述）
    - 结果重排序

    是双路检索调度的 LangChain 实现。
    """

    def __init__(
        self,
        vector_store: Optional[ChromaVectorStore] = None,
        chat_model: Optional[MultimodalChatModel] = None,
        top_k: int = 10,
    ):
        """
        初始化多模态检索器

        Args:
            vector_store: 向量存储实例，默认使用全局实例
            chat_model: 聊天模型实例，默认使用全局实例
            top_k: 返回结果数量
        """
        self.vector_store = vector_store or get_vector_store()
        self.chat_model = chat_model or get_chat_model()
        self.top_k = top_k

    def _rerank_documents(self, documents: List[Document]) -> List[Document]:
        """
        对文档进行重排序

        Args:
            documents: 文档列表

        Returns:
            List[Document]: 重排序后的文档列表
        """
        # 转换为简单重排序所需的格式
        hits = []
        for doc in documents:
            hits.append({
                "id": doc.metadata.get("id", ""),
                "document": doc.page_content,
                "metadata": doc.metadata,
                "score": doc.metadata.get("score", 0.0),
            })

        # 重排序
        reranked = simple_rerank(hits)

        # 转换回 Document 列表
        result = []
        for hit in reranked:
            doc = Document(
                page_content=hit["document"],
                metadata=hit["metadata"],
            )
            result.append(doc)

        return result

    async def image_to_image_search(
        self,
        file: UploadFile,
        top_k: Optional[int] = None,
    ) -> Tuple[List[Document], str]:
        """
        图像到图像检索

        先用多模态模型生成输入图像的描述，再基于描述进行文本检索。

        Args:
            file: 上传的图像文件
            top_k: 返回结果数量，默认使用初始化时的值

        Returns:
            Tuple[List[Document], str]: (检索结果列表, 生成的描述)
        """
        k = top_k or self.top_k

        # 读取文件内容
        contents = await file.read()
        # 将图像转为 base64 编码
        b64_image = base64.b64encode(contents).decode("utf-8")

        # 生成图像描述
        description = await self.chat_model.agenerate_description(
            image_b64=b64_image,
            prompt=IMAGE_DESCRIPTION_PROMPT,
        )

        # 基于描述进行文本检索
        results = self.vector_store.similarity_search_with_score(description, k=k)

        # 转换为 Document 列表
        documents = []
        for doc, score in results:
            doc.metadata["score"] = float(score)
            documents.append(doc)

        # 重排序
        reranked = self._rerank_documents(documents)

        return reranked, description

    async def text_to_image_search(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Document]:
        """
        文本到图像检索

        Args:
            query: 查询文本
            top_k: 返回结果数量，默认使用初始化时的值

        Returns:
            List[Document]: 检索结果列表
        """
        k = top_k or self.top_k

        # 文本到图像检索
        results = self.vector_store.similarity_search_with_score(query, k=k)

        # 转换为 Document 列表
        documents = []
        for doc, score in results:
            doc.metadata["score"] = float(score)
            documents.append(doc)

        # 重排序
        return self._rerank_documents(documents)

    def search_with_dict_output(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        检索并返回字典格式结果（兼容现有接口）

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        k = top_k or self.top_k
        documents = self.vector_store.search_by_text(query, top_k=k)
        return simple_rerank(documents)


# 全局检索器实例缓存
_retriever: Optional[MultimodalRetriever] = None


def get_multimodal_retriever(
    top_k: int = 10,
) -> MultimodalRetriever:
    """
    获取多模态检索器实例（单例模式）

    Args:
        top_k: 返回结果数量

    Returns:
        MultimodalRetriever: 检索器实例
    """
    global _retriever
    if _retriever is None:
        _retriever = MultimodalRetriever(top_k=top_k)
    return _retriever
