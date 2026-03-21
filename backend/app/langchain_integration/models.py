"""
LangChain 模型集成模块

该模块提供基于 LangChain 的模型客户端实现，包括：
- 多模态聊天模型（MultimodalChatModel）
- 嵌入模型（EmbeddingModel）

使用 LangChain 的标准接口封装现有的模型服务，实现与 LangChain 生态的无缝集成。
"""
import base64
from typing import Any, Dict, List, Optional, Union

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.embeddings import Embeddings
from pydantic import Field

from app.core.config import settings


class MultimodalChatModel(BaseChatModel):
    """
    多模态聊天模型

    基于 LangChain BaseChatModel 实现的多模态模型封装，支持：
    - 文本对话
    - 图像理解（通过 base64 编码）
    - 多图像对话

    底层使用阿里百炼/通义千问等多模态模型 API。
    """

    # 模型配置参数
    base_url: str = Field(default="")
    api_key: str = Field(default="")
    model_name: str = Field(default="")
    temperature: float = Field(default=0.7)
    max_tokens: Optional[int] = Field(default=None)

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ):
        """
        初始化多模态聊天模型

        Args:
            base_url: API 基础 URL，默认从配置读取
            api_key: API 密钥，默认从配置读取
            model_name: 模型名称，默认从配置读取
            temperature: 采样温度，控制生成随机性
            max_tokens: 最大生成 token 数
            **kwargs: 其他参数
        """
        super().__init__(**kwargs)
        self.base_url = base_url or (settings.MLLM_BASE_URL or "")
        self.api_key = api_key or (settings.MLLM_API_KEY or "")
        self.model_name = model_name or (settings.MLLM_MODEL_NAME or "")
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def _llm_type(self) -> str:
        """返回 LLM 类型标识"""
        return "multimodal-chat"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """返回模型标识参数"""
        return {
            "model_name": self.model_name,
            "base_url": self.base_url,
            "temperature": self.temperature,
        }

    def _convert_message_to_dict(self, message: BaseMessage) -> Dict[str, Any]:
        """
        将 LangChain Message 转换为 API 格式

        Args:
            message: LangChain 消息对象

        Returns:
            Dict: API 请求格式的消息字典
        """
        if isinstance(message, SystemMessage):
            return {"role": "system", "content": message.content}
        elif isinstance(message, HumanMessage):
            # 处理多模态内容（包含图像）
            content = message.content
            if isinstance(content, list):
                # 多模态内容格式
                return {"role": "user", "content": content}
            else:
                return {"role": "user", "content": content}
        elif isinstance(message, AIMessage):
            return {"role": "assistant", "content": message.content}
        else:
            return {"role": "user", "content": str(message.content)}

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        生成聊天响应（同步方法）

        Args:
            messages: 消息列表
            stop: 停止词列表
            run_manager: 回调管理器
            **kwargs: 其他参数

        Returns:
            ChatResult: 聊天生成结果
        """
        import httpx

        # 转换消息格式
        api_messages = [self._convert_message_to_dict(m) for m in messages]

        # 构建请求
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": api_messages,
            "temperature": self.temperature,
        }

        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        if stop:
            payload["stop"] = stop

        # 发送请求
        with httpx.Client(base_url=self.base_url, timeout=60) as client:
            response = client.post("/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        # 解析响应
        content = data["choices"][0]["message"]["content"]
        message = AIMessage(content=content)
        generation = ChatGeneration(message=message)

        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        异步生成聊天响应

        Args:
            messages: 消息列表
            stop: 停止词列表
            run_manager: 回调管理器
            **kwargs: 其他参数

        Returns:
            ChatResult: 聊天生成结果
        """
        import httpx

        # 转换消息格式
        api_messages = [self._convert_message_to_dict(m) for m in messages]

        # 构建请求
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": api_messages,
            "temperature": self.temperature,
        }

        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        if stop:
            payload["stop"] = stop

        # 发送异步请求
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            response = await client.post("/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        # 解析响应
        content = data["choices"][0]["message"]["content"]
        message = AIMessage(content=content)
        generation = ChatGeneration(message=message)

        return ChatResult(generations=[generation])

    async def agenerate_description(self, image_b64: str, prompt: str) -> str:
        """
        生成图像描述（异步）

        Args:
            image_b64: Base64 编码的图像数据
            prompt: 提示词

        Returns:
            str: 生成的描述文本
        """
        # 构建多模态消息内容
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ]

        messages = [HumanMessage(content=content)]
        result = await self._agenerate(messages)
        return result.generations[0].message.content


class DashScopeEmbeddings(Embeddings):
    """
    阿里百炼 DashScope 嵌入模型

    基于 LangChain Embeddings 接口实现的嵌入模型封装，支持：
    - 文本嵌入
    - 图像嵌入（通过 base64 编码）

    使用阿里百炼 dashscope SDK 调用多模态嵌入模型。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        初始化嵌入模型

        Args:
            api_key: API 密钥，默认从配置读取
            model_name: 模型名称，默认从配置读取
        """
        self.api_key = api_key or (settings.EMBEDDING_API_KEY or "")
        self.model_name = model_name or (settings.EMBEDDING_MODEL_NAME or "")

        # 设置 dashscope API 密钥
        import dashscope
        dashscope.api_key = self.api_key

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        嵌入文档文本（同步）

        Args:
            texts: 文本列表

        Returns:
            List[List[float]]: 嵌入向量列表
        """
        from dashscope import MultiModalEmbedding

        embeddings = []
        for text in texts:
            input_data = [{"text": text}]
            response = MultiModalEmbedding.call(
                model=self.model_name,
                input=input_data
            )
            if response.status_code == 200:
                embedding = response.output["embeddings"][0]["embedding"]
                embeddings.append(embedding)
            else:
                raise Exception(f"DashScope API error: {response.code} - {response.message}")
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """
        嵌入查询文本（同步）

        Args:
            text: 查询文本

        Returns:
            List[float]: 嵌入向量
        """
        embeddings = self.embed_documents([text])
        return embeddings[0]

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        异步嵌入文档文本

        Args:
            texts: 文本列表

        Returns:
            List[List[float]]: 嵌入向量列表
        """
        # DashScope SDK 是同步的，使用同步方法
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> List[float]:
        """
        异步嵌入查询文本

        Args:
            text: 查询文本

        Returns:
            List[float]: 嵌入向量
        """
        return self.embed_query(text)

    def embed_images(self, image_paths: List[str]) -> List[List[float]]:
        """
        嵌入图像文件

        Args:
            image_paths: 图像文件路径列表

        Returns:
            List[List[float]]: 嵌入向量列表
        """
        from dashscope import MultiModalEmbedding

        embeddings = []
        for image_path in image_paths:
            # 读取图像并转换为 base64
            with open(image_path, "rb") as f:
                image_data = f.read()
                image_b64 = base64.b64encode(image_data).decode("utf-8")

            input_data = [{"image": f"data:image/jpeg;base64,{image_b64}"}]
            response = MultiModalEmbedding.call(
                model=self.model_name,
                input=input_data
            )
            if response.status_code == 200:
                embedding = response.output["embeddings"][0]["embedding"]
                embeddings.append(embedding)
            else:
                raise Exception(f"DashScope API error: {response.code} - {response.message}")
        return embeddings


class OpenAIEmbeddingsWrapper(Embeddings):
    """
    OpenAI 风格嵌入模型包装器

    兼容 OpenAI /v1/embeddings 风格接口的嵌入模型封装。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        初始化嵌入模型

        Args:
            base_url: API 基础 URL，默认从配置读取
            api_key: API 密钥，默认从配置读取
            model_name: 模型名称，默认从配置读取
        """
        self.base_url = base_url or (settings.EMBEDDING_BASE_URL or "")
        self.api_key = api_key or (settings.EMBEDDING_API_KEY or "")
        self.model_name = model_name or (settings.EMBEDDING_MODEL_NAME or "")

    def embed_documents(self, texts: List[str], batch_size: int = 10) -> List[List[float]]:
        """
        嵌入文档文本（同步），自动分批避免超出 API 单次请求限制。

        Args:
            texts: 文本列表
            batch_size: 每批最多发送的文本数量，默认 25

        Returns:
            List[List[float]]: 嵌入向量列表
        """
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        all_embeddings: List[List[float]] = []
        with httpx.Client(base_url=self.base_url, timeout=60) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i: i + batch_size]
                payload = {"model": self.model_name, "input": batch}
                response = client.post("/v1/embeddings", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                all_embeddings.extend(item["embedding"] for item in data["data"])

        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        """
        嵌入查询文本（同步）

        Args:
            text: 查询文本

        Returns:
            List[float]: 嵌入向量
        """
        embeddings = self.embed_documents([text])
        return embeddings[0]

    async def aembed_documents(self, texts: List[str], batch_size: int = 10) -> List[List[float]]:
        """
        异步嵌入文档文本，自动分批避免超出 API 单次请求限制。

        Args:
            texts: 文本列表
            batch_size: 每批最多发送的文本数量，默认 25

        Returns:
            List[List[float]]: 嵌入向量列表
        """
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        all_embeddings: List[List[float]] = []
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            for i in range(0, len(texts), batch_size):
                batch = texts[i: i + batch_size]
                payload = {"model": self.model_name, "input": batch}
                response = await client.post("/v1/embeddings", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                all_embeddings.extend(item["embedding"] for item in data["data"])

        return all_embeddings

    async def aembed_query(self, text: str) -> List[float]:
        """
        异步嵌入查询文本

        Args:
            text: 查询文本

        Returns:
            List[float]: 嵌入向量
        """
        embeddings = await self.aembed_documents([text])
        return embeddings[0]


# 全局模型实例缓存
_chat_model: Optional[MultimodalChatModel] = None
_embedding_model: Optional[Embeddings] = None
_multimodal_embedding_model: Optional[Embeddings] = None


def get_chat_model() -> MultimodalChatModel:
    """
    获取多模态聊天模型实例（单例模式）

    Returns:
        MultimodalChatModel: 聊天模型实例
    """
    global _chat_model
    if _chat_model is None:
        _chat_model = MultimodalChatModel()
    return _chat_model


def get_embedding_model() -> Embeddings:
    """
    获取文本嵌入模型实例（单例模式）。

    用于主流程的文本向量检索，对应 EMBEDDING_* 配置。

    Returns:
        Embeddings: 嵌入模型实例
    """
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = OpenAIEmbeddingsWrapper()
    return _embedding_model


def get_multimodal_embedding_model() -> Embeddings:
    """
    获取多模态嵌入模型实例（单例模式）。

    仅用于 CLIP baseline，支持图文同空间编码，对应 MULTIMODAL_EMBEDDING_* 配置。

    Returns:
        DashScopeEmbeddings: 多模态嵌入模型实例
    """
    global _multimodal_embedding_model
    if _multimodal_embedding_model is None:
        _multimodal_embedding_model = DashScopeEmbeddings(
            api_key=settings.MULTIMODAL_EMBEDDING_API_KEY,
            model_name=settings.MULTIMODAL_EMBEDDING_MODEL_NAME,
        )
    return _multimodal_embedding_model
