from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings


class BaseEmbeddingClient(ABC):
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class OpenAIStyleEmbeddingClient(BaseEmbeddingClient):
    """
    兼容 OpenAI /v1/embeddings 风格接口的嵌入客户端，可对接阿里百炼等服务。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self.base_url = base_url or (settings.EMBEDDING_BASE_URL or "")
        self.api_key = api_key or (settings.EMBEDDING_API_KEY or "")
        self.model_name = model_name or (settings.EMBEDDING_MODEL_NAME or "")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "input": texts,
        }
        with httpx.Client(base_url=self.base_url, timeout=60) as client:
            resp = client.post("/v1/embeddings", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # 假设返回 data.data[i].embedding
        return [item["embedding"] for item in data["data"]]


def get_embedding_client() -> BaseEmbeddingClient:
    return OpenAIStyleEmbeddingClient()

