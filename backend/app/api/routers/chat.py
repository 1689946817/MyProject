"""
RAG 聊天 API 路由模块（LangChain 版本）

该模块定义了 RAG（检索增强生成）聊天相关的 API 路由，包括：
- RAG 聊天接口：基于用户查询（文本或图像）生成回答

使用 LangChain 框架实现，所有路由都以 /api/rag 为前缀。
"""
from typing import List, Optional

from fastapi import APIRouter, File, Form, UploadFile

from app.application.schemas import ChatResponse, SearchResultItem
from app.langchain_integration.adapters import get_langchain_adapter


# 创建 API 路由器，设置前缀和标签
router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/chat", response_model=ChatResponse)
async def rag_chat_endpoint(
    query: str = Form(...),
    top_k: int = Form(5),
    image: Optional[UploadFile] = File(None),
) -> ChatResponse:
    """RAG 聊天接口
    
    基于用户查询（文本或图像）检索相关图像，然后生成回答。
    使用 LangChain 框架实现 RAG 流程。
    
    Args:
        query: 用户问题
        top_k: 返回的检索结果数量，默认为 5
        image: 可选的上传图像，用于图像检索
    
    Returns:
        ChatResponse: 聊天结果，包含生成的回答和检索到的相关图像列表
    """
    # 调用 LangChain 适配器的 RAG 聊天服务
    adapter = get_langchain_adapter()
    answer, retrieved = await adapter.rag_chat(query=query, top_k=top_k, image=image)
    # 处理检索结果
    results: List[SearchResultItem] = []
    for item in retrieved:
        meta = item.get("metadata") or {}
        results.append(
            SearchResultItem(
                id=item.get("id"),
                file_path=meta.get("file_path"),
                description=item.get("document"),
                score=float(item.get("score", 0.0)),
            )
        )
    # 构建响应
    return ChatResponse(answer=answer, results=results)
