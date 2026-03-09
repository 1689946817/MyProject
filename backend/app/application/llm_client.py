"""
文本生成模型客户端模块

该模块定义了文本生成模型客户端的抽象基类和具体实现，用于：
- 与云端大模型服务交互
- 处理多轮对话
- 为 RAG 问答提供文本生成能力

目前实现了兼容 OpenAI 风格接口的客户端，可对接通义千问、阿里百炼等服务。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings


class BaseLLMClient(ABC):
    """文本生成模型客户端抽象基类
    
    定义了文本生成模型客户端的基本接口，所有具体实现都需要继承此类并实现抽象方法。
    """
    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """多轮对话接口
        
        发送对话消息到模型并返回模型的回复。
        
        Args:
            messages: 对话消息列表，每个消息包含 role 和 content 字段
        
        Returns:
            str: 模型的回复文本
        """
        raise NotImplementedError


class OpenAIStyleLLMClient(BaseLLMClient):
    """OpenAI 风格文本生成客户端
    
    兼容 OpenAI /v1/chat/completions 风格接口的 LLM 客户端，
    可对接通义千问、阿里百炼等云端大模型服务。
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
        self.base_url = base_url or (settings.LLM_BASE_URL or "")
        self.api_key = api_key or (settings.LLM_API_KEY or "")
        self.model_name = model_name or (settings.LLM_MODEL_NAME or "")

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """发送对话消息并获取回复
        
        使用 OpenAI 风格的接口发送对话消息到模型并返回回复。
        
        Args:
            messages: 对话消息列表，每个消息包含 role 和 content 字段
        
        Returns:
            str: 模型的回复文本
        
        Raises:
            httpx.HTTPError: API 调用失败时抛出
        """
        # 构建请求头
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # 构建请求体
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
        }
        
        # 发送异步请求
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            resp = await client.post("/v1/chat/completions", headers=headers, json=payload)
            # 检查响应状态
            resp.raise_for_status()
            data = resp.json()
        
        # 解析响应，返回模型回复
        return data["choices"][0]["message"]["content"]


def get_llm_client() -> BaseLLMClient:
    """获取文本生成模型客户端实例
    
    返回 OpenAIStyleLLMClient 实例，用于与云端大模型服务交互。
    
    Returns:
        BaseLLMClient: 文本生成模型客户端实例
    """
    return OpenAIStyleLLMClient()

