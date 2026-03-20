"""
配置管理模块

该模块负责加载和管理应用程序的所有配置项，包括：
- 应用基本信息
- CORS 配置
- 数据库连接
- 向量存储配置
- 模型服务配置（多模态、嵌入、文本生成）

使用 pydantic-settings 从环境变量或 .env 文件加载配置，确保类型安全和默认值处理。
"""
import os
from functools import lru_cache
from typing import List, Optional

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings

# config.py 所在目录的绝对路径（backend/app/core/）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# backend/ 目录（.env 文件所在位置）
_BACKEND_DIR = os.path.dirname(os.path.dirname(_BASE_DIR))


class Settings(BaseSettings):
    """应用配置类
    
    管理所有应用配置项，支持从环境变量和 .env 文件加载。
    配置项采用大写命名，保持与环境变量一致。
    """
    # 应用基本信息
    APP_NAME: str = "Multimodal RAG Base"  # 应用名称

    # 后端 CORS 配置
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
    ]  # 允许的跨域来源，主要是前端开发服务器地址

    # 数据库配置
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///./app.db"  # SQLite 数据库连接字符串

    # Chroma 向量存储配置
    CHROMA_PERSIST_DIR: str = os.path.join(_BASE_DIR, "../../chroma_data")  # Chroma 持久化存储目录（绝对路径，固定指向 backend/chroma_data/）
    CHROMA_COLLECTION_NAME: str = "images_semantic_desc"  # 向量存储集合名称，用于存储图像语义描述

    # 多模态模型配置（例如 阿里百炼上的 Qwen-VL）
    MLLM_BASE_URL: Optional[str] = None  # 多模态模型 API 基础 URL
    MLLM_API_KEY: Optional[str] = None  # 多模态模型 API 密钥
    MLLM_MODEL_NAME: Optional[str] = None  # 多模态模型名称

    # 嵌入模型配置（文本向量，用于主流程）
    EMBEDDING_BASE_URL: Optional[str] = None  # 嵌入模型 API 基础 URL
    EMBEDDING_API_KEY: Optional[str] = None  # 嵌入模型 API 密钥
    EMBEDDING_MODEL_NAME: Optional[str] = None  # 嵌入模型名称

    # 多模态嵌入模型配置（图文同空间，仅用于 CLIP baseline）
    MULTIMODAL_EMBEDDING_API_KEY: Optional[str] = None
    MULTIMODAL_EMBEDDING_MODEL_NAME: Optional[str] = None

    # RAG 问答用的文本生成模型配置
    LLM_BASE_URL: Optional[str] = None  # 文本生成模型 API 基础 URL
    LLM_API_KEY: Optional[str] = None  # 文本生成模型 API 密钥
    LLM_MODEL_NAME: Optional[str] = None  # 文本生成模型名称

    class Config:
        """配置类的配置
        
        控制配置加载行为：
        - case_sensitive: 环境变量大小写敏感
        - env_file: 从 .env 文件加载配置
        - env_file_encoding: .env 文件编码
        """
        case_sensitive = True
        env_file = os.path.join(_BACKEND_DIR, ".env")
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """获取应用配置
    
    使用 lru_cache 缓存配置实例，避免重复加载。
    
    Returns:
        Settings: 应用配置实例
    """
    return Settings()


# 全局配置实例，供其他模块直接使用
settings = get_settings()

