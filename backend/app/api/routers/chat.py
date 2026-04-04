"""
RAG 聊天 API 路由模块（LangChain 版本）。
"""
import json
import os
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.application.chat_service import (
    ChatSessionNotFoundError,
    add_message,
    create_session,
    delete_session,
    get_recent_history,
    get_session_or_raise,
    list_sessions,
    load_message_sources,
    load_json_field,
    dump_json_field,
)
from app.application.schemas import (
    ChatMessageOut,
    ChatResponse,
    ChatSessionCreateResponse,
    ChatSessionDetailResponse,
    ChatSessionRenameRequest,
    ChatSourceItem,
    DeleteResponse,
    SearchResultItem,
)
from app.core.config import settings
from app.data.database import get_db
from app.langchain_integration.adapters import get_langchain_adapter


router = APIRouter(tags=["chat"])
rag_router = APIRouter(prefix="/api/rag", tags=["rag"])


def _build_results(retrieved: List[dict]) -> List[SearchResultItem]:
    results: List[SearchResultItem] = []
    for item in retrieved:
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata") or {}
        result_id = item.get("id") or meta.get("id") or item.get("doc_id") or meta.get("doc_id")
        if result_id is None:
            continue
        description = item.get("document") or item.get("content")
        results.append(
            SearchResultItem(
                id=str(result_id),
                file_path=meta.get("file_path"),
                description=description,
                score=float(item.get("score", 0.0)),
            )
        )
    return results


def _safe_score(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fallback_source_id(item: dict, metadata: dict[str, Any]) -> str:
    candidates = [
        item.get("id"),
        metadata.get("id"),
        item.get("doc_id"),
        metadata.get("doc_id"),
        metadata.get("file_path"),
        item.get("document"),
        item.get("content"),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text:
            return text
    return "unknown-source"


def _normalize_chat_sources(retrieved: List[dict]) -> List[ChatSourceItem]:
    normalized: List[ChatSourceItem] = []
    for item in retrieved:
        if not isinstance(item, dict):
            continue

        raw_metadata = item.get("metadata")
        metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        is_document_chunk = item.get("doc_id") is not None or item.get("chunk_index") is not None or "content" in item

        if is_document_chunk:
            doc_id = item.get("doc_id") or metadata.get("doc_id") or item.get("id") or metadata.get("id")
            chunk_index = item.get("chunk_index")
            if chunk_index is None:
                chunk_index = metadata.get("chunk_index")
            if doc_id is not None:
                metadata.setdefault("doc_id", doc_id)
            if chunk_index is not None:
                metadata.setdefault("chunk_index", chunk_index)

            source_id = (
                f"{doc_id}#chunk-{chunk_index}"
                if doc_id is not None and chunk_index is not None
                else _fallback_source_id(item, metadata)
            )
            file_path = metadata.get("file_path")
            title = metadata.get("file_name")
            if not title and file_path:
                title = os.path.basename(file_path)
            if not title:
                title = str(doc_id or source_id)

            normalized.append(
                ChatSourceItem(
                    source_type="document_chunk",
                    source_id=str(source_id),
                    title=title,
                    file_path=file_path,
                    content=item.get("content"),
                    score=_safe_score(item.get("score")),
                    metadata=metadata,
                )
            )
            continue

        source_id = item.get("id") or metadata.get("id") or _fallback_source_id(item, metadata)
        file_path = metadata.get("file_path")
        title = metadata.get("filename")
        if not title and file_path:
            title = os.path.basename(file_path)
        if not title:
            title = str(source_id)

        normalized.append(
            ChatSourceItem(
                source_type="image",
                source_id=str(source_id),
                title=title,
                file_path=file_path,
                content=item.get("document"),
                score=_safe_score(item.get("score")),
                metadata=metadata,
            )
        )
    return normalized


def _to_chat_message_out(message) -> ChatMessageOut:
    sources = [ChatSourceItem.model_validate(item) for item in load_message_sources(getattr(message, "sources_json", None))]
    retrieval_params = load_json_field(getattr(message, "retrieval_params_json", None))
    return ChatMessageOut(
        id=message.id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        has_image=message.has_image,
        sources=sources,
        retrieval_params=retrieval_params,
        created_at=message.created_at,
    )


@router.post("/api/chat/sessions", response_model=ChatSessionCreateResponse)
def create_chat_session(db: Session = Depends(get_db)) -> ChatSessionCreateResponse:
    session = create_session(db)
    return ChatSessionCreateResponse.model_validate(session)


@router.get("/api/chat/sessions", response_model=List[ChatSessionCreateResponse])
def list_chat_sessions(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[ChatSessionCreateResponse]:
    sessions = list_sessions(db, limit=limit, offset=offset)
    return [ChatSessionCreateResponse.model_validate(session) for session in sessions]


@router.get("/api/chat/sessions/{session_id}", response_model=ChatSessionDetailResponse)
def get_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> ChatSessionDetailResponse:
    try:
        session = get_session_or_raise(db, session_id)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    return ChatSessionDetailResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[_to_chat_message_out(message) for message in session.messages],
    )


@router.patch("/api/chat/sessions/{session_id}", response_model=ChatSessionCreateResponse)
def rename_chat_session(
    session_id: str,
    body: ChatSessionRenameRequest,
    db: Session = Depends(get_db),
) -> ChatSessionCreateResponse:
    try:
        session = get_session_or_raise(db, session_id)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    session.title = body.title
    db.add(session)
    db.commit()
    db.refresh(session)
    return ChatSessionCreateResponse.model_validate(session)


@router.delete("/api/chat/sessions/{session_id}", response_model=DeleteResponse)
def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> DeleteResponse:
    success = delete_session(db, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    return DeleteResponse(success=True)


@rag_router.post("/chat", response_model=ChatResponse)
async def rag_chat_endpoint(
    query: str = Form(...),
    top_k: int = Form(5),
    session_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """RAG 聊天接口（支持持久化多轮对话）。"""
    try:
        session = get_session_or_raise(db, session_id) if session_id else create_session(db)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    history = get_recent_history(db, session.id, settings.CHAT_HISTORY_MAX_TURNS)

    adapter = get_langchain_adapter()
    answer, retrieved = await adapter.rag_chat(
        query=query,
        top_k=top_k,
        image=image,
        chat_history=history,
    )
    sources = _normalize_chat_sources(retrieved)

    retrieval_params = {"top_k": top_k, "has_image": image is not None, "query": query, "stream": False}
    add_message(db, session, "user", query, has_image=image is not None, retrieval_params=retrieval_params)
    add_message(
        db,
        session,
        "assistant",
        answer,
        sources=[source.model_dump() for source in sources],
        retrieval_params=retrieval_params,
    )

    return ChatResponse(
        answer=answer,
        results=_build_results(retrieved),
        sources=sources,
        session_id=session.id,
    )


@rag_router.post("/chat/stream")
async def rag_chat_stream_endpoint(
    query: str = Form(...),
    top_k: int = Form(5),
    session_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """RAG 聊天流式接口（SSE）。"""
    try:
        session = get_session_or_raise(db, session_id) if session_id else create_session(db)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    history = get_recent_history(db, session.id, settings.CHAT_HISTORY_MAX_TURNS)
    adapter = get_langchain_adapter()

    async def event_generator():
        yield f"data: {json.dumps({'type': 'session', 'session_id': session.id})}\n\n"

        full_answer = ""
        retrieved_docs = []

        async for chunk, docs in adapter.rag_chat_stream(
            query=query,
            top_k=top_k,
            image=image,
            chat_history=history,
        ):
            full_answer += chunk
            retrieved_docs = docs
            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

        retrieval_params = {"top_k": top_k, "has_image": image is not None, "query": query, "stream": True}
        add_message(db, session, "user", query, has_image=image is not None, retrieval_params=retrieval_params)
        sources = _normalize_chat_sources(retrieved_docs)
        add_message(
            db,
            session,
            "assistant",
            full_answer,
            sources=[source.model_dump() for source in sources],
            retrieval_params=retrieval_params,
        )

        yield f"data: {json.dumps({'type': 'results', 'results': [item.model_dump() for item in _build_results(retrieved_docs)], 'sources': [source.model_dump() for source in sources]})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
