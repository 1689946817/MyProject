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
    load_json_list,
    load_json_field,
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
    TimingSummary,
)
from app.core.config import settings
from app.core.timing import RequestTimingCollector, bind_timing_collector
from app.data.database import get_db
from app.langchain_integration.adapters import get_langchain_adapter
from app.retrieval.relevance import annotate_relevance


router = APIRouter(tags=["chat"])
rag_router = APIRouter(prefix="/api/rag", tags=["rag"])

VALID_EXECUTION_HINTS = {
    "auto",
    "direct_llm",
    "multimodal_rag",
    "image_similarity",
    "image_grounded_answer",
    "uploaded_image_qa",
    "save_uploaded_image",
}


def _maybe_timings_payload(collector: RequestTimingCollector):
    if not settings.EXPOSE_TIMINGS_IN_API:
        return None
    return TimingSummary.model_validate(collector.snapshot())


def _parse_source_scope_json(raw_scope: Optional[str]) -> Optional[dict[str, list[str]]]:
    if not raw_scope:
        return None
    try:
        payload = json.loads(raw_scope)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="source_scope_json 必须是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="source_scope_json 必须是对象")

    scope: dict[str, list[str]] = {}
    for key in ("doc_ids", "image_ids"):
        value = payload.get(key, [])
        if value is None:
            value = []
        if not isinstance(value, list):
            raise HTTPException(status_code=422, detail=f"source_scope_json.{key} 必须是字符串数组")
        normalized = [str(item).strip() for item in value if str(item).strip()]
        if normalized:
            scope[key] = normalized
    return scope or None


def _normalize_execution_hint(execution_hint: Optional[str]) -> Optional[str]:
    if not execution_hint:
        return None
    normalized = execution_hint.strip()
    if not normalized or normalized == "auto":
        return None
    if normalized not in VALID_EXECUTION_HINTS:
        raise HTTPException(status_code=422, detail=f"不支持的 execution_hint: {normalized}")
    return normalized


def _build_results(retrieved: List[dict]) -> List[SearchResultItem]:
    results: List[SearchResultItem] = []
    for item in retrieved:
        if not isinstance(item, dict):
            continue
        annotate_relevance(item)
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
                relevance_score=_safe_score(item.get("relevance_score") or meta.get("relevance_score")),
                score_source=item.get("score_source") or meta.get("score_source"),
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

        annotate_relevance(item)

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
                    rerank_score=_safe_score(item.get("rerank_score") or metadata.get("rerank_score")),
                    relevance_score=_safe_score(item.get("relevance_score") or metadata.get("relevance_score")),
                    score_source=item.get("score_source") or metadata.get("score_source"),
                    metadata=metadata,
                )
            )
            continue

        source_id = item.get("id") or metadata.get("id") or _fallback_source_id(item, metadata)
        file_path = metadata.get("file_path")
        title = metadata.get("title") or metadata.get("filename")
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
                rerank_score=_safe_score(item.get("rerank_score") or metadata.get("rerank_score")),
                relevance_score=_safe_score(item.get("relevance_score") or metadata.get("relevance_score")),
                score_source=item.get("score_source") or metadata.get("score_source"),
                metadata=metadata,
            )
        )
    return normalized


def _to_chat_message_out(message) -> ChatMessageOut:
    sources = [ChatSourceItem.model_validate(item) for item in load_message_sources(getattr(message, "sources_json", None))]
    retrieval_params = load_json_field(getattr(message, "retrieval_params_json", None))
    retrieval_steps = load_json_list(getattr(message, "retrieval_steps_json", None))
    return ChatMessageOut(
        id=message.id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        has_image=message.has_image,
        sources=sources,
        retrieval_params=retrieval_params,
        retrieval_steps=retrieval_steps,
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


@router.delete("/api/chat/sessions/{session_id}", response_model=DeleteResponse, response_model_exclude_defaults=True)
def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> DeleteResponse:
    success = delete_session(db, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    return DeleteResponse(success=True)


def _coerce_rag_chat_result(
    result: Any,
    *,
    has_uploaded_image: bool,
) -> tuple[str, List[dict], dict[str, Any]]:
    if isinstance(result, tuple) and len(result) == 3:
        answer, retrieved, intent = result
        return answer, retrieved, intent
    if isinstance(result, tuple) and len(result) == 2:
        answer, retrieved = result
        return answer, retrieved, {
            "presentation_mode": "rag_answer",
            "execution_mode": "multimodal_rag",
            "use_rag": True,
            "has_uploaded_image": has_uploaded_image,
            "wants_images": has_uploaded_image,
            "confidence": 1.0,
            "reason": "legacy_adapter_result",
            "retrieval_steps": [],
        }
    raise ValueError("Unsupported rag_chat result shape")


@rag_router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
async def rag_chat_endpoint(
    query: str = Form(...),
    top_k: Optional[int] = Form(None),
    enable_score_filter: Optional[bool] = Form(None),
    min_relevance_score: Optional[float] = Form(None),
    execution_hint: Optional[str] = Form(None),
    source_scope_json: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """RAG 聊天接口（支持持久化多轮对话）。"""
    resolved_execution_hint = _normalize_execution_hint(execution_hint)
    source_scope = _parse_source_scope_json(source_scope_json)
    resolved_top_k = top_k or settings.CHAT_DEFAULT_TOP_K
    resolved_enable_score_filter = (
        enable_score_filter
        if enable_score_filter is not None
        else settings.CHAT_ENABLE_SCORE_FILTER
    )
    resolved_min_relevance_score = (
        min_relevance_score
        if min_relevance_score is not None
        else settings.CHAT_MIN_RELEVANCE_SCORE
    )
    collector = RequestTimingCollector("/api/rag/chat", "rag_chat")
    collector.set_metadata(
        top_k=resolved_top_k,
        has_uploaded_image=image is not None,
        enable_score_filter=resolved_enable_score_filter,
        min_relevance_score=resolved_min_relevance_score,
        execution_hint=resolved_execution_hint,
        source_scope=source_scope,
    )
    response: ChatResponse | None = None
    try:
        with bind_timing_collector(collector), collector.stage(
            "rag_chat_total",
            meta={
                "top_k": resolved_top_k,
                "has_uploaded_image": image is not None,
                "enable_score_filter": resolved_enable_score_filter,
                "min_relevance_score": resolved_min_relevance_score,
                "execution_hint": resolved_execution_hint,
                "source_scope": source_scope,
            },
        ):
            try:
                with collector.stage("chat_session_load"):
                    session = get_session_or_raise(db, session_id) if session_id else create_session(db)
            except ChatSessionNotFoundError as exc:
                raise HTTPException(status_code=404, detail="会话不存在") from exc

            with collector.stage("chat_history_load"):
                history = get_recent_history(db, session.id, settings.CHAT_HISTORY_MAX_TURNS)

            adapter = get_langchain_adapter()
            result = await adapter.rag_chat(
                query=query,
                top_k=resolved_top_k,
                image=image,
                chat_history=history,
                enable_score_filter=resolved_enable_score_filter,
                min_relevance_score=resolved_min_relevance_score,
                execution_hint=resolved_execution_hint,
                source_scope=source_scope,
            )
            answer, retrieved, intent = _coerce_rag_chat_result(
                result,
                has_uploaded_image=image is not None,
            )
            collector.set_metadata(
                execution_mode=intent.get("execution_mode"),
                presentation_mode=intent.get("presentation_mode"),
            )
            sources = _normalize_chat_sources(retrieved)
            retrieval_steps = intent.get("retrieval_steps") or []

            retrieval_params = {
                "top_k": resolved_top_k,
                "has_image": image is not None,
                "query": query,
                "stream": False,
                "enable_score_filter": resolved_enable_score_filter,
                "min_relevance_score": resolved_min_relevance_score,
                "execution_hint": resolved_execution_hint,
                "source_scope": source_scope,
                "presentation_mode": intent.get("presentation_mode"),
                "execution_mode": intent.get("execution_mode"),
                "use_rag": intent.get("use_rag"),
                "classifier_reason": intent.get("reason"),
                "classifier_confidence": intent.get("confidence"),
            }
            with collector.stage("chat_message_persist"):
                add_message(db, session, "user", query, has_image=image is not None, retrieval_params=retrieval_params)
                add_message(
                    db,
                    session,
                    "assistant",
                    answer,
                    sources=[source.model_dump() for source in sources],
                    retrieval_params=retrieval_params,
                    retrieval_steps=retrieval_steps,
                )

            response = ChatResponse(
                answer=answer,
                results=_build_results(retrieved),
                sources=sources,
                session_id=session.id,
                presentation_mode=intent.get("presentation_mode", "rag_answer"),
                execution_mode=intent.get("execution_mode", "multimodal_rag"),
                use_rag=bool(intent.get("use_rag", True)),
                has_uploaded_image=image is not None,
                retrieval_steps=retrieval_steps,
            )
        if settings.EXPOSE_TIMINGS_IN_API and response is not None:
            response.timings = _maybe_timings_payload(collector)
        return response
    finally:
        collector.finish(log_enabled=settings.ENABLE_TIMING_LOGS)


@rag_router.post("/chat/stream")
async def rag_chat_stream_endpoint(
    query: str = Form(...),
    top_k: Optional[int] = Form(None),
    enable_score_filter: Optional[bool] = Form(None),
    min_relevance_score: Optional[float] = Form(None),
    execution_hint: Optional[str] = Form(None),
    source_scope_json: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """RAG 聊天流式接口（SSE）。"""
    resolved_execution_hint = _normalize_execution_hint(execution_hint)
    source_scope = _parse_source_scope_json(source_scope_json)
    resolved_top_k = top_k or settings.CHAT_DEFAULT_TOP_K
    resolved_enable_score_filter = (
        enable_score_filter
        if enable_score_filter is not None
        else settings.CHAT_ENABLE_SCORE_FILTER
    )
    resolved_min_relevance_score = (
        min_relevance_score
        if min_relevance_score is not None
        else settings.CHAT_MIN_RELEVANCE_SCORE
    )
    collector = RequestTimingCollector("/api/rag/chat/stream", "rag_chat_stream")
    collector.set_metadata(
        top_k=resolved_top_k,
        has_uploaded_image=image is not None,
        enable_score_filter=resolved_enable_score_filter,
        min_relevance_score=resolved_min_relevance_score,
        execution_hint=resolved_execution_hint,
        source_scope=source_scope,
    )
    try:
        with collector.stage("chat_session_load"):
            session = get_session_or_raise(db, session_id) if session_id else create_session(db)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    with collector.stage("chat_history_load"):
        history = get_recent_history(db, session.id, settings.CHAT_HISTORY_MAX_TURNS)
    adapter = get_langchain_adapter()

    async def event_generator():
        with bind_timing_collector(collector), collector.stage(
            "rag_chat_stream_total",
            meta={
                "top_k": resolved_top_k,
                "has_uploaded_image": image is not None,
                "enable_score_filter": resolved_enable_score_filter,
                "min_relevance_score": resolved_min_relevance_score,
                "execution_hint": resolved_execution_hint,
                "source_scope": source_scope,
            },
        ):
            try:
                yield f"data: {json.dumps({'type': 'session', 'session_id': session.id})}\n\n"

                full_answer = ""
                retrieved_docs = []
                final_intent = None

                try:
                    stream = adapter.rag_chat_stream(
                        query=query,
                        top_k=resolved_top_k,
                        image=image,
                        chat_history=history,
                        enable_score_filter=resolved_enable_score_filter,
                        min_relevance_score=resolved_min_relevance_score,
                        execution_hint=resolved_execution_hint,
                        source_scope=source_scope,
                    )
                except TypeError:
                    stream = adapter.rag_chat_stream(
                        query=query,
                        top_k=resolved_top_k,
                        chat_history=history,
                        enable_score_filter=resolved_enable_score_filter,
                        min_relevance_score=resolved_min_relevance_score,
                    )

                async for event in stream:
                    if len(event) == 3:
                        chunk, docs, intent = event
                    elif len(event) == 2:
                        chunk, docs = event
                        intent = None
                    else:
                        raise ValueError("Unsupported rag_chat_stream event shape")
                    full_answer += chunk
                    retrieved_docs = docs
                    if intent is not None:
                        final_intent = intent
                        collector.set_metadata(
                            execution_mode=intent.get("execution_mode"),
                            presentation_mode=intent.get("presentation_mode"),
                        )
                    collector.mark_first_token()
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                retrieval_params = {
                    "top_k": resolved_top_k,
                    "has_image": image is not None,
                    "query": query,
                    "stream": True,
                    "enable_score_filter": resolved_enable_score_filter,
                    "min_relevance_score": resolved_min_relevance_score,
                    "execution_hint": resolved_execution_hint,
                    "source_scope": source_scope,
                }
                with collector.stage("chat_message_persist"):
                    add_message(db, session, "user", query, has_image=image is not None, retrieval_params=retrieval_params)
                    sources = _normalize_chat_sources(retrieved_docs)
                    retrieval_steps = (final_intent or {}).get("retrieval_steps") or []
                    add_message(
                        db,
                        session,
                        "assistant",
                        full_answer,
                        sources=[source.model_dump() for source in sources],
                        retrieval_params=retrieval_params,
                        retrieval_steps=retrieval_steps,
                    )

                results_payload = {
                    "type": "results",
                    "results": [item.model_dump() for item in _build_results(retrieved_docs)],
                    "sources": [source.model_dump() for source in sources],
                    "retrieval_steps": retrieval_steps,
                }
                if settings.EXPOSE_TIMINGS_IN_API:
                    results_payload["timings"] = TimingSummary.model_validate(collector.snapshot()).model_dump()
                yield f"data: {json.dumps(results_payload)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                collector.finish(log_enabled=settings.ENABLE_TIMING_LOGS)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
