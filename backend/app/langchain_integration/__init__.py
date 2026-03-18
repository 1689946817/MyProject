"""
LangChain 集成模块

该模块提供基于 LangChain 框架重构的多模态 RAG 系统核心组件，包括：
- 模型客户端（MLLM、Embedding、LLM）
- 向量存储和检索器
- RAG Chain 和 Agent
- 与现有系统的适配器

遵循 LangChain 最佳实践，使用 LCEL（LangChain Expression Language）构建可组合的链式流程。
"""

from app.langchain_integration.models import (
    get_chat_model,
    get_embedding_model,
    MultimodalChatModel,
)
from app.langchain_integration.vectorstores import (
    ChromaVectorStore,
    get_vector_store,
)
from app.langchain_integration.retrievers import (
    MultimodalRetriever,
    get_multimodal_retriever,
)
from app.langchain_integration.chains import (
    ImageDescriptionChain,
    RAGChain,
    get_image_description_chain,
    get_rag_chain,
)
from app.langchain_integration.adapters import (
    LangChainAdapter,
    get_langchain_adapter,
)

__all__ = [
    # 模型
    "get_chat_model",
    "get_embedding_model",
    "MultimodalChatModel",
    # 向量存储
    "ChromaVectorStore",
    "get_vector_store",
    # 检索器
    "MultimodalRetriever",
    "get_multimodal_retriever",
    # Chain
    "ImageDescriptionChain",
    "RAGChain",
    "get_image_description_chain",
    "get_rag_chain",
    # 适配器
    "LangChainAdapter",
    "get_langchain_adapter",
]
