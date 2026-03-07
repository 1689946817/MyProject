from functools import lru_cache
from typing import List, Optional

from pydantic import AnyHttpUrl, BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Multimodal RAG Knowledge Base"

    # Backend
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Database
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///./app.db"

    # Chroma / vector store
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    CHROMA_COLLECTION_NAME: str = "images_semantic_desc"

    # Multimodal model (e.g. Qwen-VL on 阿里百炼)
    MLLM_BASE_URL: Optional[str] = None
    MLLM_API_KEY: Optional[str] = None
    MLLM_MODEL_NAME: Optional[str] = None

    # Embedding model (e.g. BGE-m3 on 阿里百炼 / OpenAI 格式)
    EMBEDDING_BASE_URL: Optional[str] = None
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_MODEL_NAME: Optional[str] = None

    # LLM for RAG QA
    LLM_BASE_URL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL_NAME: Optional[str] = None

    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

