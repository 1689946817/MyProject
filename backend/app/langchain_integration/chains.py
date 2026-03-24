"""
LangChain Chain 集成模块

该模块提供基于 LangChain LCEL（LangChain Expression Language）的 Chain 实现，包括：
- 图像描述生成 Chain
- RAG 问答 Chain

使用 LCEL 构建可组合的链式流程，遵循 LangChain 最佳实践。
"""
import base64
import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough, RunnableSequence

from app.langchain_integration.models import (
    build_image_data_url,
    get_chat_model,
    guess_image_mime_type,
    MultimodalChatModel,
)
from app.langchain_integration.retrievers import MultimodalRetriever, get_multimodal_retriever
from app.semantic.prompts import IMAGE_DESCRIPTION_PROMPT


class ImageDescriptionChain:
    """
    图像描述生成 Chain

    使用 LCEL 构建的图像描述生成链，流程：
    1. 接收图像（base64 编码）
    2. 调用多模态模型生成描述
    3. 返回结构化描述文本

    基于 LangChain Runnable 接口实现，支持同步和异步执行。
    """

    def __init__(
        self,
        chat_model: Optional[MultimodalChatModel] = None,
        prompt: Optional[str] = None,
    ):
        """
        初始化图像描述生成 Chain

        Args:
            chat_model: 聊天模型实例，默认使用全局实例
            prompt: 提示词模板，默认使用 IMAGE_DESCRIPTION_PROMPT
        """
        self.chat_model = chat_model or get_chat_model()
        self.prompt = prompt or IMAGE_DESCRIPTION_PROMPT

        # 构建 LCEL Chain
        self._chain = self._build_chain()

    def _build_chain(self) -> RunnableSequence:
        """
        构建 LCEL Chain

        Returns:
            RunnableSequence: 可运行的 Chain
        """
        # 定义 Chain 组件
        # 1. 准备输入：提取图像和提示词
        prepare_input = RunnableLambda(
            lambda x: {
                "image_b64": x["image_b64"],
                "mime_type": x.get("mime_type", "image/jpeg"),
                "prompt": x.get("prompt", self.prompt),
            }
        )

        # 2. 构建多模态消息
        def build_messages(inputs: Dict[str, Any]) -> List[HumanMessage]:
            content = [
                {"type": "text", "text": inputs["prompt"]},
                {
                    "type": "image_url",
                    "image_url": {"url": build_image_data_url(inputs["image_b64"], inputs["mime_type"])},
                },
            ]
            return [HumanMessage(content=content)]

        build_msg_runnable = RunnableLambda(build_messages)

        # 3. 调用模型
        call_model = self.chat_model

        # 4. 解析输出
        output_parser = StrOutputParser()

        # 组合 Chain
        chain = prepare_input | build_msg_runnable | call_model | output_parser

        return chain

    def invoke(self, inputs: Dict[str, Any]) -> str:
        """
        同步执行 Chain

        Args:
            inputs: 输入字典，包含 image_b64 和可选的 prompt

        Returns:
            str: 生成的描述文本
        """
        return self._chain.invoke(inputs)

    async def ainvoke(self, inputs: Dict[str, Any]) -> str:
        """
        异步执行 Chain

        Args:
            inputs: 输入字典，包含 image_b64 和可选的 prompt

        Returns:
            str: 生成的描述文本
        """
        return await self._chain.ainvoke(inputs)

    async def ainvoke_from_uploadfile(self, file: UploadFile) -> str:
        """
        从 UploadFile 异步生成描述

        Args:
            file: 上传的图像文件

        Returns:
            str: 生成的描述文本
        """
        contents = await file.read()
        b64_image = base64.b64encode(contents).decode("utf-8")
        mime_type = file.content_type or "image/jpeg"
        return await self.ainvoke({"image_b64": b64_image, "mime_type": mime_type})


class RAGChain:
    """
    RAG 问答 Chain

    使用 LCEL 构建的检索增强生成链，流程：
    1. 接收用户查询（文本或图像）
    2. 执行检索获取相关图像
    3. 构建多模态提示（查询 + 检索到的图像）
    4. 调用多模态模型生成回答
    5. 返回回答和引用

    基于 LangChain Runnable 接口实现，支持同步和异步执行。
    """

    def __init__(
        self,
        chat_model: Optional[MultimodalChatModel] = None,
        retriever: Optional[MultimodalRetriever] = None,
        top_k: int = 5,
    ):
        """
        初始化 RAG Chain

        Args:
            chat_model: 聊天模型实例，默认使用全局实例
            retriever: 检索器实例，默认使用全局实例
            top_k: 检索结果数量
        """
        self.chat_model = chat_model or get_chat_model()
        self.retriever = retriever or get_multimodal_retriever(top_k=top_k)
        self.top_k = top_k

        # 构建 LCEL Chain
        self._chain = self._build_chain()

    def _build_chain(self) -> RunnableSequence:
        """
        构建 LCEL Chain

        Returns:
            RunnableSequence: 可运行的 Chain
        """
        # 定义系统提示词
        system_prompt = (
            "你是一个多模态知识库问答助手。你将看到若干张检索到的相关图像，"
            "以及用户提出的问题。请仔细观察这些图像的内容，基于图像中的视觉信息回答用户的问题。\n\n"
            "请基于图像内容进行回答，可以自然地引用相关图像，例如'根据第一张图像，可以看到……'。"
            "如果图像信息不足以回答某些部分，请明确说明不确定。"
        )

        # 1. 检索步骤
        def retrieve_documents(inputs: Dict[str, Any]) -> Dict[str, Any]:
            query = inputs["query"]
            # 使用检索器获取相关文档
            documents = self.retriever.search_with_dict_output(query, top_k=self.top_k)
            return {
                "query": query,
                "documents": documents,
            }

        retrieve_runnable = RunnableLambda(retrieve_documents)

        # 2. 准备多模态消息
        def prepare_messages(inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
            query = inputs["query"]
            documents = inputs["documents"]

            # 构建消息内容
            content = []

            # 添加系统提示词
            content.append({"type": "text", "text": system_prompt})

            # 添加用户问题
            content.append({"type": "text", "text": f"\n\n用户问题：{query}\n\n"})

            # 添加检索到的图像
            for idx, doc in enumerate(documents, start=1):
                meta = doc.get("metadata") or {}
                file_path = meta.get("file_path", "")

                if file_path and os.path.exists(file_path):
                    try:
                        with open(file_path, "rb") as f:
                            image_data = f.read()
                            image_b64 = base64.b64encode(image_data).decode("utf-8")

                        mime_type = guess_image_mime_type(file_path)
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": build_image_data_url(image_b64, mime_type)},
                        })
                        content.append({
                            "type": "text",
                            "text": f"\n[图像 {idx}]",
                        })
                    except Exception as e:
                        print(f"警告：无法读取图像文件 {file_path}: {e}")

            return [HumanMessage(content=content)]

        prepare_msg_runnable = RunnableLambda(prepare_messages)

        # 3. 调用模型
        call_model = self.chat_model

        # 4. 解析输出
        output_parser = StrOutputParser()

        # 组合 Chain
        chain = retrieve_runnable | prepare_msg_runnable | call_model | output_parser

        return chain

    def invoke(self, inputs: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        """
        同步执行 RAG Chain

        Args:
            inputs: 输入字典，包含 query

        Returns:
            Tuple[str, List[Dict]]: (生成的回答, 检索结果列表)
        """
        query = inputs["query"]

        # 执行检索
        documents = self.retriever.search_with_dict_output(query, top_k=self.top_k)

        # 执行 Chain 生成回答
        answer = self._chain.invoke(inputs)

        return answer, documents

    async def ainvoke(self, inputs: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        """
        异步执行 RAG Chain

        Args:
            inputs: 输入字典，包含 query

        Returns:
            Tuple[str, List[Dict]]: (生成的回答, 检索结果列表)
        """
        query = inputs["query"]

        # 执行检索
        documents = self.retriever.search_with_dict_output(query, top_k=self.top_k)

        # 执行 Chain 生成回答
        answer = await self._chain.ainvoke(inputs)

        return answer, documents

    async def ainvoke_with_image(
        self,
        query: str,
        image: UploadFile,
        top_k: Optional[int] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        使用图像查询执行 RAG Chain

        Args:
            query: 用户问题
            image: 上传的图像文件
            top_k: 检索结果数量

        Returns:
            Tuple[str, List[Dict]]: (生成的回答, 检索结果列表)
        """
        k = top_k or self.top_k

        # 执行图像到图像检索
        documents, description = await self.retriever.image_to_image_search(image, top_k=k)

        # 将 Document 转换为字典格式
        dict_documents = []
        for doc in documents:
            dict_documents.append({
                "id": doc.metadata.get("id", ""),
                "document": doc.page_content,
                "metadata": doc.metadata,
                "score": doc.metadata.get("score", 0.0),
            })

        # 使用生成的描述作为查询执行 RAG
        inputs = {"query": description}
        answer = await self._chain.ainvoke(inputs)

        return answer, dict_documents


# 全局 Chain 实例缓存
_image_description_chain: Optional[ImageDescriptionChain] = None
_rag_chain: Optional[RAGChain] = None


def get_image_description_chain() -> ImageDescriptionChain:
    """
    获取图像描述生成 Chain 实例（单例模式）

    Returns:
        ImageDescriptionChain: Chain 实例
    """
    global _image_description_chain
    if _image_description_chain is None:
        _image_description_chain = ImageDescriptionChain()
    return _image_description_chain


def get_rag_chain(top_k: int = 5) -> RAGChain:
    """
    获取 RAG Chain 实例（单例模式）

    Args:
        top_k: 检索结果数量

    Returns:
        RAGChain: Chain 实例
    """
    global _rag_chain
    if _rag_chain is None:
        _rag_chain = RAGChain(top_k=top_k)
    return _rag_chain
