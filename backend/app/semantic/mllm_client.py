from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings


class BaseMLLMClient(ABC):
    @abstractmethod
    async def generate_description(self, image_b64: str, prompt: str) -> str:
        """根据 base64 编码的图片和提示词生成结构化描述。"""
        raise NotImplementedError


class QwenVLClient(BaseMLLMClient):
    """
    面向阿里百炼 / 通义千问多模态接口的简单封装。
    具体的 base_url、api_key、model_name 通过环境变量配置。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self.base_url = base_url or (settings.MLLM_BASE_URL or "")
        self.api_key = api_key or (settings.MLLM_API_KEY or "")
        self.model_name = model_name or (settings.MLLM_MODEL_NAME or "")

    async def generate_description(self, image_b64: str, prompt: str) -> str:
        # 这里采用兼容 OpenAI 的 /chat/completions 风格请求体
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # 具体字段需根据实际百炼/服务商文档调整，这里给出兼容 OpenAI 多模态的占位结构
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

        async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as client:
            resp = await client.post("/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # 根据 OpenAI 风格响应解析文本
        return data["choices"][0]["message"]["content"]


def get_mllm_client() -> BaseMLLMClient:
    # 目前默认返回 QwenVLClient，后续可以在此扩展不同提供商的多模态模型。
    return QwenVLClient()

