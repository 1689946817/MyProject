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
from app.application.chat_citations import build_chat_citations
from app.application.operations import get_feedback_for_message, record_feedback
from app.application.schemas import (
    AnswerFeedbackOut,
    AnswerFeedbackRequest,
    ChatCitationItem,
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
from app.data.chat_models import ChatMessage
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
            if metadata.get("file_path") and not metadata.get("file_name"):
                metadata.setdefault("file_name", os.path.basename(metadata["file_path"]))

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
        if file_path and not metadata.get("file_name"):
            metadata.setdefault("file_name", os.path.basename(file_path))
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
    feedback = get_feedback_for_message(message._sa_instance_state.session, message.id)
    citations = []
    if isinstance(retrieval_params, dict):
        citations = [
            ChatCitationItem.model_validate(item)
            for item in retrieval_params.get("citations", [])
            if isinstance(item, dict)
        ]
    return ChatMessageOut(
        id=message.id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        has_image=message.has_image,
        sources=sources,
        citations=citations,
        retrieval_params=retrieval_params,
        retrieval_steps=retrieval_steps,
        feedback=AnswerFeedbackOut.model_validate(feedback) if feedback is not None else None,
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


@router.post("/api/chat/messages/{message_id}/feedback", response_model=AnswerFeedbackOut)
def submit_message_feedback(
    message_id: int,
    body: AnswerFeedbackRequest,
    db: Session = Depends(get_db),
) -> AnswerFeedbackOut:
    assistant_message = (
        db.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.role == "assistant")
        .first()
    )
    if assistant_message is None:
        raise HTTPException(status_code=404, detail="助手消息不存在")

    session = get_session_or_raise(db, assistant_message.session_id)
    query = None
    messages = list(session.messages)
    for index, item in enumerate(messages):
        if item.id != assistant_message.id or index == 0:
            continue
        previous = messages[index - 1]
        if previous.role == "user":
            query = previous.content
        break

    retrieval_params = load_json_field(getattr(assistant_message, "retrieval_params_json", None)) or {}
    retrieval_steps = load_json_list(getattr(assistant_message, "retrieval_steps_json", None))
    sources = load_message_sources(getattr(assistant_message, "sources_json", None))
    feedback = record_feedback(
        db,
        assistant_message=assistant_message,
        rating=body.rating,
        issue_types=body.issue_types,
        comment=body.comment,
        query=query,
        retrieval_snapshot={
            "retrieval_params": retrieval_params,
            "retrieval_steps": retrieval_steps,
            "sources": sources,
        },
    )
    return AnswerFeedbackOut.model_validate(feedback)


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


def _build_default_stream_intent(*, has_uploaded_image: bool) -> dict[str, Any]:
    return {
        "presentation_mode": "rag_answer",
        "execution_mode": "multimodal_rag",
        "use_rag": True,
        "has_uploaded_image": has_uploaded_image,
        "wants_images": has_uploaded_image,
        "confidence": 1.0,
        "reason": "stream_default_intent",
        "retrieval_steps": [],
    }


def _build_retrieval_params(
    *,
    query: str,
    resolved_top_k: int,
    image: Optional[UploadFile],
    resolved_enable_score_filter: bool,
    resolved_min_relevance_score: Optional[float],
    resolved_execution_hint: Optional[str],
    source_scope: Optional[dict[str, list[str]]],
    intent: dict[str, Any],
    stream: bool,
) -> dict[str, Any]:
    return {
        "top_k": resolved_top_k,
        "has_image": image is not None,
        "query": query,
        "stream": stream,
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


def _build_chat_response(
    *,
    answer: str,
    retrieved: List[dict],
    sources: List[ChatSourceItem],
    citations: List[ChatCitationItem],
    session_id: str,
    intent: dict[str, Any],
    collector: RequestTimingCollector,
) -> ChatResponse:
    response = ChatResponse(
        answer=answer,
        results=_build_results(retrieved),
        sources=sources,
        session_id=session_id,
        presentation_mode=intent.get("presentation_mode", "rag_answer"),
        execution_mode=intent.get("execution_mode", "multimodal_rag"),
        use_rag=bool(intent.get("use_rag", True)),
        has_uploaded_image=bool(intent.get("has_uploaded_image", False)),
        retrieval_steps=intent.get("retrieval_steps") or [],
        citations=citations,
    )
    if settings.EXPOSE_TIMINGS_IN_API:
        response.timings = _maybe_timings_payload(collector)
    return response


def _build_results_payload(
    *,
    retrieved: List[dict],
    sources: List[ChatSourceItem],
    citations: List[ChatCitationItem],
    intent: dict[str, Any],
    collector: RequestTimingCollector,
) -> dict[str, Any]:
    payload = {
        "type": "results",
        "results": [item.model_dump() for item in _build_results(retrieved)],
        "sources": [source.model_dump() for source in sources],
        "retrieval_steps": intent.get("retrieval_steps") or [],
        "presentation_mode": intent.get("presentation_mode", "rag_answer"),
        "execution_mode": intent.get("execution_mode", "multimodal_rag"),
        "use_rag": bool(intent.get("use_rag", True)),
        "has_uploaded_image": bool(intent.get("has_uploaded_image", False)),
        "citations": [citation.model_dump() for citation in citations],
    }
    if settings.EXPOSE_TIMINGS_IN_API:
        payload["timings"] = TimingSummary.model_validate(collector.snapshot()).model_dump()
    return payload


async def _prepare_rag_chat_context(
    *,
    query: str,
    top_k: Optional[int],
    enable_score_filter: Optional[bool],
    min_relevance_score: Optional[float],
    execution_hint: Optional[str],
    source_scope_json: Optional[str],
    session_id: Optional[str],
    image: Optional[UploadFile],
    db: Session,
    request_path: str,
    request_kind: str,
) -> tuple[
    RequestTimingCollector,
    Any,
    list[tuple[str, str]],
    Optional[str],
    Optional[dict[str, list[str]]],
    int,
    bool,
    Optional[float],
]:
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
    collector = RequestTimingCollector(request_path, request_kind)
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

    return (
        collector,
        session,
        history,
        resolved_execution_hint,
        source_scope,
        resolved_top_k,
        resolved_enable_score_filter,
        resolved_min_relevance_score,
    )


def _build_sse_chunk(payload: Any) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _normalize_stream_text_chunk(chunk: Any) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk

    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content

    message = getattr(chunk, "message", None)
    if message is not None:
        message_content = getattr(message, "content", None)
        if isinstance(message_content, str):
            return message_content

    raise TypeError(f"Unsupported streaming chunk type: {type(chunk).__name__}")


def _build_rag_streaming_response(
    *,
    query: str,
    image: Optional[UploadFile],
    db: Session,
    collector: RequestTimingCollector,
    session: Any,
    history: list[tuple[str, str]],
    resolved_execution_hint: Optional[str],
    source_scope: Optional[dict[str, list[str]]],
    resolved_top_k: int,
    resolved_enable_score_filter: bool,
    resolved_min_relevance_score: Optional[float],
    request_stage_name: str,
) -> StreamingResponse:
    adapter = get_langchain_adapter()

    async def event_generator():
        with bind_timing_collector(collector), collector.stage(
            request_stage_name,
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
                yield _build_sse_chunk({"type": "session", "session_id": session.id})

                full_answer = ""
                retrieved_docs: List[dict] = []
                final_intent: Optional[dict[str, Any]] = None

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

                first_chunk_sent = False
                async for event in stream:
                    if len(event) == 3:
                        chunk, docs, intent = event
                    elif len(event) == 2:
                        chunk, docs = event
                        intent = None
                    else:
                        raise ValueError("Unsupported rag_chat_stream event shape")

                    chunk = _normalize_stream_text_chunk(chunk)
                    full_answer += chunk
                    retrieved_docs = docs
                    if intent is not None:
                        final_intent = intent
                        collector.set_metadata(
                            execution_mode=intent.get("execution_mode"),
                            presentation_mode=intent.get("presentation_mode"),
                        )
                    if chunk:
                        if not first_chunk_sent:
                            collector.mark_first_token()
                            first_chunk_sent = True
                        yield _build_sse_chunk({"type": "content", "content": chunk})

                final_intent = final_intent or _build_default_stream_intent(has_uploaded_image=image is not None)
                collector.set_metadata(
                    execution_mode=final_intent.get("execution_mode"),
                    presentation_mode=final_intent.get("presentation_mode"),
                )
                retrieval_params = _build_retrieval_params(
                    query=query,
                    resolved_top_k=resolved_top_k,
                    image=image,
                    resolved_enable_score_filter=resolved_enable_score_filter,
                    resolved_min_relevance_score=resolved_min_relevance_score,
                    resolved_execution_hint=resolved_execution_hint,
                    source_scope=source_scope,
                    intent=final_intent,
                    stream=True,
                )
                sources = _normalize_chat_sources(retrieved_docs)
                citations = build_chat_citations(full_answer, sources)
                retrieval_steps = final_intent.get("retrieval_steps") or []
                with collector.stage("chat_message_persist"):
                    add_message(db, session, "user", query, has_image=image is not None, retrieval_params=retrieval_params)
                    assistant_retrieval_params = {
                        **retrieval_params,
                        "citations": [citation.model_dump() for citation in citations],
                        "timings": TimingSummary.model_validate(collector.snapshot()).model_dump() if settings.EXPOSE_TIMINGS_IN_API else None,
                    }
                    add_message(
                        db,
                        session,
                        "assistant",
                        full_answer,
                        sources=[source.model_dump() for source in sources],
                        retrieval_params=assistant_retrieval_params,
                        retrieval_steps=retrieval_steps,
                    )

                yield _build_sse_chunk(
                    _build_results_payload(
                        retrieved=retrieved_docs,
                        sources=sources,
                        citations=citations,
                        intent={
                            **final_intent,
                            "retrieval_steps": retrieval_steps,
                            "has_uploaded_image": image is not None,
                        },
                        collector=collector,
                    )
                )
            except Exception as exc:
                yield _build_sse_chunk({"type": "error", "detail": str(exc)})
            finally:
                yield "data: [DONE]\n\n"
                collector.finish(log_enabled=settings.ENABLE_TIMING_LOGS)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@rag_router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
async def rag_chat_endpoint(
    query: str = Form(...),
    top_k: Optional[int] = Form(None),
    enable_score_filter: Optional[bool] = Form(None),
    min_relevance_score: Optional[float] = Form(None),
    execution_hint: Optional[str] = Form(None),
    source_scope_json: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    stream: bool = Form(False),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
) -> Any:
    """RAG 聊天接口（支持 JSON 与 SSE 双模式）。"""
    (
        collector,
        session,
        history,
        resolved_execution_hint,
        source_scope,
        resolved_top_k,
        resolved_enable_score_filter,
        resolved_min_relevance_score,
    ) = await _prepare_rag_chat_context(
        query=query,
        top_k=top_k,
        enable_score_filter=enable_score_filter,
        min_relevance_score=min_relevance_score,
        execution_hint=execution_hint,
        source_scope_json=source_scope_json,
        session_id=session_id,
        image=image,
        db=db,
        request_path="/api/rag/chat",
        request_kind="rag_chat_stream" if stream else "rag_chat",
    )
    if stream:
        return _build_rag_streaming_response(
            query=query,
            image=image,
            db=db,
            collector=collector,
            session=session,
            history=history,
            resolved_execution_hint=resolved_execution_hint,
            source_scope=source_scope,
            resolved_top_k=resolved_top_k,
            resolved_enable_score_filter=resolved_enable_score_filter,
            resolved_min_relevance_score=resolved_min_relevance_score,
            request_stage_name="rag_chat_stream_total",
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
            citations = build_chat_citations(answer, sources)
            retrieval_steps = intent.get("retrieval_steps") or []
            retrieval_params = _build_retrieval_params(
                query=query,
                resolved_top_k=resolved_top_k,
                image=image,
                resolved_enable_score_filter=resolved_enable_score_filter,
                resolved_min_relevance_score=resolved_min_relevance_score,
                resolved_execution_hint=resolved_execution_hint,
                source_scope=source_scope,
                intent=intent,
                stream=False,
            )
            with collector.stage("chat_message_persist"):
                add_message(db, session, "user", query, has_image=image is not None, retrieval_params=retrieval_params)
                assistant_retrieval_params = {
                    **retrieval_params,
                    "citations": [citation.model_dump() for citation in citations],
                    "timings": _maybe_timings_payload(collector).model_dump() if settings.EXPOSE_TIMINGS_IN_API else None,
                }
                add_message(
                    db,
                    session,
                    "assistant",
                    answer,
                    sources=[source.model_dump() for source in sources],
                    retrieval_params=assistant_retrieval_params,
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
                citations=citations,
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
    (
        collector,
        session,
        history,
        resolved_execution_hint,
        source_scope,
        resolved_top_k,
        resolved_enable_score_filter,
        resolved_min_relevance_score,
    ) = await _prepare_rag_chat_context(
        query=query,
        top_k=top_k,
        enable_score_filter=enable_score_filter,
        min_relevance_score=min_relevance_score,
        execution_hint=execution_hint,
        source_scope_json=source_scope_json,
        session_id=session_id,
        image=image,
        db=db,
        request_path="/api/rag/chat/stream",
        request_kind="rag_chat_stream",
    )
    return _build_rag_streaming_response(
        query=query,
        image=image,
        db=db,
        collector=collector,
        session=session,
        history=history,
        resolved_execution_hint=resolved_execution_hint,
        source_scope=source_scope,
        resolved_top_k=resolved_top_k,
        resolved_enable_score_filter=resolved_enable_score_filter,
        resolved_min_relevance_score=resolved_min_relevance_score,
        request_stage_name="rag_chat_stream_total",
    )
