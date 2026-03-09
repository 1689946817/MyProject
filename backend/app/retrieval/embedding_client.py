"""
嵌入模型客户端模块

该模块定义了嵌入模型客户端的抽象基类和具体实现，用于：
- 生成文本的向量嵌入
- 封装不同提供商的嵌入模型接口

支持两种类型的嵌入客户端：
1. OpenAIStyleEmbeddingClient：兼容 OpenAI 风格接口的客户端
2. DashScopeEmbeddingClient：使用阿里百炼 dashscope SDK 的客户端
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import dashscope
from dashscope import MultiModalEmbedding

from app.core.config import settings


class BaseEmbeddingClient(ABC):
    """嵌入模型客户端抽象基类

    定义了嵌入模型客户端的基本接口，所有具体实现都需要继承此类并实现抽象方法。
    """
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """生成文本的向量嵌入

        Args:
            texts: 文本列表

        Returns:
            List[List[float]]: 向量嵌入列表，每个文本对应一个向量
        """
        raise NotImplementedError

    @abstractmethod
    def embed_images(self, image_paths: List[str]) -> List[List[float]]:
        """生成图像的向量嵌入

        Args:
            image_paths: 图像文件路径列表

        Returns:
            List[List[float]]: 向量嵌入列表，每个图像对应一个向量
        """
        raise NotImplementedError


class OpenAIStyleEmbeddingClient(BaseEmbeddingClient):
    """OpenAI 风格嵌入客户端
    
    兼容 OpenAI /v1/embeddings 风格接口的嵌入客户端，可对接阿里百炼等服务。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """初始化客户端
        
        Args:
            base_url: API 基础 URL，若不提供则使用配置文件中的值
            api_key: API 密钥，若不提供则使用配置文件中的值
            model_name: 模型名称，若不提供则使用配置文件中的值
        """
        self.base_url = base_url or (settings.EMBEDDING_BASE_URL or "")
        self.api_key = api_key or (settings.EMBEDDING_API_KEY or "")
        self.model_name = model_name or (settings.EMBEDDING_MODEL_NAME or "")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """生成文本的向量嵌入

        使用 OpenAI 风格的接口生成文本嵌入。

        Args:
            texts: 文本列表

        Returns:
            List[List[float]]: 向量嵌入列表

        Raises:
            httpx.HTTPError: API 调用失败时抛出
        """
        import httpx

        # 构建请求头
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # 构建请求体
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "input": texts,
        }

        # 发送请求
        with httpx.Client(base_url=self.base_url, timeout=60) as client:
            resp = client.post("/v1/embeddings", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # 解析响应，返回嵌入向量
        return [item["embedding"] for item in data["data"]]

    def embed_images(self, image_paths: List[str]) -> List[List[float]]:
        """生成图像的向量嵌入

        OpenAI 风格的接口通常不支持图像嵌入，这里抛出 NotImplementedError。

        Args:
            image_paths: 图像文件路径列表

        Returns:
            List[List[float]]: 向量嵌入列表

        Raises:
            NotImplementedError: OpenAI 风格接口不支持图像嵌入
        """
        raise NotImplementedError("OpenAI style embedding client does not support image embedding")


class DashScopeEmbeddingClient(BaseEmbeddingClient):
    """阿里百炼嵌入客户端
    
    使用阿里百炼 dashscope SDK 的嵌入客户端，支持 qwen3-vl-embedding 等多模态模型。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """初始化客户端
        
        Args:
            api_key: API 密钥，若不提供则使用配置文件中的值
            model_name: 模型名称，若不提供则使用配置文件中的值
        """
        self.api_key = api_key or (settings.EMBEDDING_API_KEY or "")
        self.model_name = model_name or (settings.EMBEDDING_MODEL_NAME or "")
        # 设置 dashscope API 密钥
        dashscope.api_key = self.api_key

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """生成文本的向量嵌入

        使用阿里百炼 dashscope SDK 生成文本嵌入。

        Args:
            texts: 文本列表

        Returns:
            List[List[float]]: 向量嵌入列表

        Raises:
            Exception: API 调用失败时抛出
        """
        embeddings = []
        # 逐文本生成嵌入
        for text in texts:
            input_data = [{'text': text}]
            response = MultiModalEmbedding.call(
                model=self.model_name,
                input=input_data
            )
            if response.status_code == 200:
                embedding = response.output['embeddings'][0]['embedding']
                embeddings.append(embedding)
            else:
                raise Exception(f"DashScope API error: {response.code} - {response.message}")
        return embeddings

    def embed_images(self, image_paths: List[str]) -> List[List[float]]:
        """生成图像的向量嵌入

        使用阿里百炼 dashscope SDK 生成图像嵌入。

        Args:
            image_paths: 图像文件路径列表

        Returns:
            List[List[float]]: 向量嵌入列表

        Raises:
            Exception: API 调用失败时抛出
        """
        import base64

        embeddings = []
        # 逐图像生成嵌入
        for image_path in image_paths:
            # 读取图像文件并转换为 base64
            try:
                with open(image_path, 'rb') as image_file:
                    image_data = image_file.read()
                    image_base64 = base64.b64encode(image_data).decode('utf-8')
            except Exception as e:
                raise Exception(f"Failed to read image file {image_path}: {e}")

            # 构建输入数据，使用 base64 编码的图像
            input_data = [{'image': f"data:image/jpeg;base64,{image_base64}"}]

            response = MultiModalEmbedding.call(
                model=self.model_name,
                input=input_data
            )
            if response.status_code == 200:
                embedding = response.output['embeddings'][0]['embedding']
                embeddings.append(embedding)
            else:
                raise Exception(f"DashScope API error: {response.code} - {response.message}")
        return embeddings


def get_embedding_client() -> BaseEmbeddingClient:
    """获取嵌入模型客户端实例
    
    根据配置返回合适的嵌入模型客户端：
    - 如果模型是 qwen3-vl-embedding，返回 DashScopeEmbeddingClient
    - 否则返回 OpenAIStyleEmbeddingClient
    
    Returns:
        BaseEmbeddingClient: 嵌入模型客户端实例
    """
    model_name = settings.EMBEDDING_MODEL_NAME or ""
    if model_name == "qwen3-vl-embedding":
        return DashScopeEmbeddingClient()
    return OpenAIStyleEmbeddingClient()
