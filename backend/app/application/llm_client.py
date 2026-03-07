from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings


class BaseLLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """多轮对话接口，返回模型回复文本。"""
        raise NotImplementedError


class OpenAIStyleLLMClient(BaseLLMClient):
    """
    兼容 OpenAI /v1/chat/completions 风格接口的 LLM 客户端，
    可对接通义千问、阿里百炼等云端大模型服务。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self.base_url = base_url or (settings.LLM_BASE_URL or "")
        self.api_key = api_key or (settings.LLM_API_KEY or "")
        self.model_name = model_name or (settings.LLM_MODEL_NAME or "")

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            resp = await client.post("/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]


def get_llm_client() -> BaseLLMClient:
    return OpenAIStyleLLMClient()

