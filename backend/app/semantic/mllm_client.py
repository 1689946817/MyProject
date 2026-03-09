"""
多模态模型客户端模块

该模块定义了多模态模型客户端的抽象基类和具体实现，用于：
- 生成图像的结构化语义描述
- 封装不同提供商的多模态模型接口（目前支持阿里百炼/通义千问）

采用抽象基类设计，便于后续扩展其他多模态模型提供商。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings


class BaseMLLMClient(ABC):
    """多模态模型客户端抽象基类
    
    定义了多模态模型客户端的基本接口，所有具体实现都需要继承此类并实现抽象方法。
    """
    @abstractmethod
    async def generate_description(self, image_b64: str, prompt: str) -> str:
        """根据 base64 编码的图片和提示词生成结构化描述

        Args:
            image_b64: Base64 编码的图像数据
            prompt: 提示词，指导模型生成描述的方向

        Returns:
            str: 生成的结构化描述文本
        """
        raise NotImplementedError

    @abstractmethod
    async def chat_with_images(self, content: List[Dict[str, Any]]) -> str:
        """基于多图像内容进行聊天

        Args:
            content: 消息内容列表，包含文本和图像

        Returns:
            str: 生成的回答文本
        """
        raise NotImplementedError


class QwenVLClient(BaseMLLMClient):
    """通义千问多模态模型客户端
    
    面向阿里百炼 / 通义千问多模态接口的封装，使用兼容 OpenAI 的接口格式。
    具体的 base_url、api_key、model_name 通过环境变量配置。
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
        self.base_url = base_url or (settings.MLLM_BASE_URL or "")
        self.api_key = api_key or (settings.MLLM_API_KEY or "")
        self.model_name = model_name or (settings.MLLM_MODEL_NAME or "")

    async def generate_description(self, image_b64: str, prompt: str) -> str:
        """生成图像描述
        
        使用通义千问多模态模型生成图像的结构化描述。
        
        Args:
            image_b64: Base64 编码的图像数据
            prompt: 提示词，指导模型生成描述的方向
        
        Returns:
            str: 生成的结构化描述文本
        
        Raises:
            httpx.HTTPError: API 调用失败时抛出
        """
        # 构建请求头，包含认证信息
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # 构建请求体，采用兼容 OpenAI 的 /chat/completions 风格
        # 具体字段需根据实际百炼/服务商文档调整
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                            },
                        },
                    ],
                }
            ],
        }

        # 发送异步请求，设置 60 秒超时
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            resp = await client.post("/v1/chat/completions", headers=headers, json=payload)
            # 检查响应状态，若失败则抛出异常
            resp.raise_for_status()
            data = resp.json()

        # 解析响应，返回生成的描述文本
        return data["choices"][0]["message"]["content"]

    async def chat_with_images(self, content: List[Dict[str, Any]]) -> str:
        """基于多图像内容进行聊天

        Args:
            content: 消息内容列表，包含文本和图像

        Returns:
            str: 生成的回答文本

        Raises:
            httpx.HTTPError: API 调用失败时抛出
        """
        # 构建请求头，包含认证信息
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # 构建请求体，采用兼容 OpenAI 的 /chat/completions 风格
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
        }

        # 发送异步请求，设置 60 秒超时
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            resp = await client.post("/v1/chat/completions", headers=headers, json=payload)
            # 检查响应状态，若失败则抛出异常
            resp.raise_for_status()
            data = resp.json()

        # 解析响应，返回生成的回答文本
        return data["choices"][0]["message"]["content"]


def get_mllm_client() -> BaseMLLMClient:
    """获取多模态模型客户端实例
    
    根据配置返回合适的多模态模型客户端。
    目前默认返回 QwenVLClient，后续可以在此扩展不同提供商的多模态模型。
    
    Returns:
        BaseMLLMClient: 多模态模型客户端实例
    """
    return QwenVLClient()

