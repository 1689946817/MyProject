"""
RAG 聊天 API 路由模块（LangChain 版本）

该模块定义了 RAG（检索增强生成）聊天相关的 API 路由，包括：
- RAG 聊天接口：基于用户查询（文本或图像）生成回答
- 支持多轮对话（session_id）

使用 LangChain 框架实现，所有路由都以 /api/rag 为前缀。
"""
import uuid
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, File, Form, UploadFile

from app.application.schemas import ChatResponse, SearchResultItem
from app.core.config import settings
from app.langchain_integration.adapters import get_langchain_adapter


# 创建 API 路由器，设置前缀和标签
router = APIRouter(prefix="/api/rag", tags=["rag"])

# 内存会话存储：session_id → [(query, answer), ...]
_chat_sessions: OrderedDict[str, List[Tuple[str, str]]] = OrderedDict()
_MAX_SESSIONS = 200  # 最多保留的会话数


def _get_history(session_id: Optional[str]) -> List[Tuple[str, str]]:
    """获取会话历史"""
    if not session_id or session_id not in _chat_sessions:
        return []
    return _chat_sessions[session_id]


def _save_turn(session_id: str, query: str, answer: str) -> None:
    """保存一轮对话"""
    if session_id not in _chat_sessions:
        _chat_sessions[session_id] = []
        # LRU 淘汰
        while len(_chat_sessions) > _MAX_SESSIONS:
            _chat_sessions.popitem(last=False)
    history = _chat_sessions[session_id]
    history.append((query, answer))
    # 只保留最近 N 轮
    max_turns = settings.CHAT_HISTORY_MAX_TURNS
    if len(history) > max_turns:
        _chat_sessions[session_id] = history[-max_turns:]


@router.post("/chat", response_model=ChatResponse)
async def rag_chat_endpoint(
    query: str = Form(...),
    top_k: int = Form(5),
    session_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
) -> ChatResponse:
    """RAG 聊天接口（支持多轮对话）"""
    # 生成或复用 session_id
    sid = session_id or str(uuid.uuid4())

    # 获取历史
    history = _get_history(sid)

    # 调用 LangChain 适配器的 RAG 聊天服务
    adapter = get_langchain_adapter()
    answer, retrieved = await adapter.rag_chat(
        query=query, top_k=top_k, image=image, chat_history=history,
    )

    # 保存本轮对话
    _save_turn(sid, query, answer)

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
    return ChatResponse(answer=answer, results=results, session_id=sid)
