"""
RAG 聊天 API 路由模块（LangChain 版本）。

本模块提供多模态 RAG（Retrieval-Augmented Generation）聊天的核心 API 端点，
支持基于 SSE（Server-Sent Events）的流式响应和传统 JSON 响应两种模式。

## 架构概览

### SSE 流式架构
流式响应采用 SSE 协议，通过 `StreamingResponse` 向客户端推送事件流。
每个事件为一行 `data: {json}\n\n` 格式，包含以下事件类型：
- `session`：会话信息（session_id）
- `progress`：处理阶段进度（routing / retrieval / generate / complete）
- `content`：流式文本块（LLM 逐 token 生成的片段）
- `results`：最终检索结果、来源、引用、耗时等
- `error`：异常信息
流结束时发送 `data: [DONE]\n\n`。

### 会话管理
聊天会话持久化在 SQLite 数据库中，每个会话包含多条消息记录。
支持创建、列表、查询、重命名、删除会话，以及消息级反馈。

### RAG 聊天流程
1. 参数校验与归一化（execution_hint、chat_mode、source_scope 等）
2. 会话加载或创建 + 历史消息读取
3. 调用 LangChainAdapter 执行双路检索 + LLM 生成回答
4. 构建来源（sources）、引用（citations）、检索步骤（retrieval_steps）
5. 将用户消息和助手回答持久化到数据库
6. 返回 ChatResponse（JSON）或 SSE 流

### 路由注册
- `rag_router`：`/api/rag/chat`（JSON）和 `/api/rag/chat/stream`（SSE）
- `router`：会话管理 CRUD + 反馈提交
"""
import asyncio
import json
import os
import uuid
from pathlib import Path
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
from app.data.storage import get_chat_upload_path
from app.langchain_integration.adapters import get_langchain_adapter
from app.retrieval.relevance import annotate_relevance


# ---- 路由与常量定义 ----

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
VALID_CHAT_MODES = {"fast", "default", "expert"}
CHAT_UPLOAD_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
CHAT_UPLOAD_CONTENT_TYPE_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}


# ---- 参数校验/工具函数 ----


def _maybe_timings_payload(collector: RequestTimingCollector):
    """根据配置决定是否生成耗时统计 payload。

    仅当 `EXPOSE_TIMINGS_IN_API` 为 True 时，才将 RequestTimingCollector
    的快照转换为 TimingSummary 对象返回；否则返回 None。
    """
    if not settings.EXPOSE_TIMINGS_IN_API:
        return None
    return TimingSummary.model_validate(collector.snapshot())


def _parse_source_scope_json(raw_scope: Optional[str]) -> Optional[dict[str, list[str]]]:
    """解析 source_scope_json 字符串参数为结构化作用域字典。

    期望 JSON 对象格式，支持 `doc_ids` 和 `image_ids` 两个键，
    值为字符串数组。解析失败或格式非法时抛出 HTTP 422 异常。
    返回 `None` 表示不限定作用域。
    """
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
    """归一化 execution_hint 参数。

    空值或 "auto" 统一映射为 None（走自动路由）。不在白名单中的值抛出 HTTP 422。
    合法值包括：direct_llm、multimodal_rag、image_similarity、
    image_grounded_answer、uploaded_image_qa、save_uploaded_image。
    """
    if not execution_hint:
        return None
    normalized = execution_hint.strip()
    if not normalized or normalized == "auto":
        return None
    if normalized not in VALID_EXECUTION_HINTS:
        raise HTTPException(status_code=422, detail=f"不支持的 execution_hint: {normalized}")
    return normalized


def _safe_chat_upload_suffix(image: UploadFile) -> str:
    """根据上传文件名和 MIME 类型选择安全的图片扩展名。"""
    suffix = Path(image.filename or "").suffix.lower()
    if suffix in CHAT_UPLOAD_IMAGE_SUFFIXES:
        return suffix
    return CHAT_UPLOAD_CONTENT_TYPE_SUFFIXES.get((image.content_type or "").lower(), ".jpg")


async def _persist_uploaded_chat_image(image: Optional[UploadFile]) -> tuple[Optional[str], Optional[str]]:
    """保存聊天上传图，返回可由 /static 访问的文件路径和原始文件名。"""
    if image is None:
        return None, None

    suffix = _safe_chat_upload_suffix(image)
    storage_path = get_chat_upload_path(str(uuid.uuid4()), suffix)
    contents = await image.read()
    storage_path.write_bytes(contents)
    await image.seek(0)
    return str(storage_path), image.filename or storage_path.name


def _normalize_chat_mode(chat_mode: Optional[str]) -> str:
    """归一化 chat_mode 参数。

    空值默认为 "default"。合法值：fast、default、expert。
    不在白名单中的值抛出 HTTP 422。
    """
    if not chat_mode:
        return "default"
    normalized = chat_mode.strip().lower()
    if not normalized:
        return "default"
    if normalized not in VALID_CHAT_MODES:
        raise HTTPException(status_code=422, detail=f"不支持的 chat_mode: {normalized}")
    return normalized


def _build_results(retrieved: List[dict]) -> List[SearchResultItem]:
    """将检索原始结果列表转换为 SearchResultItem 列表。

    遍历每条检索结果，调用 `annotate_relevance` 注入相关性评分，
    提取 id、file_path、description、score 等字段构建标准化响应项。
    缺少 id 的条目会被跳过。
    """
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
    """安全地将值转换为浮点数评分。

    输入为 None 或无法转换时返回 None，避免类型异常。
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fallback_source_id(item: dict, metadata: dict[str, Any]) -> str:
    """从检索结果的多个候选字段中提取 source_id。

    按优先级依次尝试 id、doc_id、file_path、document、content，
    取第一个非空非空白的值。全部为空时返回 "unknown-source"。
    """
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
    """将检索原始结果列表归一化为 ChatSourceItem 列表。

    根据结果类型分为两种处理路径：
    - document_chunk：含 doc_id/chunk_index 的文档分片，source_id 格式为 `{doc_id}#chunk-{index}`
    - image：图片检索结果，source_id 直接取 id 字段

    每条结果都注入 rerank_score、relevance_score、score_source 等元数据。
    """
    normalized: List[ChatSourceItem] = []
    for item in retrieved:
        if not isinstance(item, dict):
            continue

        annotate_relevance(item)

        raw_metadata = item.get("metadata")
        metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        is_web_source = (
            item.get("source_type") == "web"
            or metadata.get("source_type") == "web"
            or metadata.get("asset_type") == "web"
        )
        if is_web_source:
            url = item.get("url") or metadata.get("url") or metadata.get("file_path")
            title = item.get("title") or metadata.get("title") or metadata.get("site_name") or url
            source_id = item.get("id") or metadata.get("id") or url or _fallback_source_id(item, metadata)
            metadata.setdefault("source_type", "web")
            metadata.setdefault("asset_type", "web")
            if url:
                metadata.setdefault("url", url)
            normalized.append(
                ChatSourceItem(
                    source_type="web",
                    source_id=str(source_id),
                    title=str(title or source_id),
                    file_path=str(url) if url else None,
                    content=item.get("content") or item.get("document"),
                    score=None,
                    rerank_score=_safe_score(item.get("rerank_score") or metadata.get("rerank_score")),
                    relevance_score=None,
                    score_source="web_search",
                    metadata=metadata,
                )
            )
            continue

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
    """将 ORM ChatMessage 对象转换为 ChatMessageOut 响应模型。

    从消息的 JSON 字段中解析 sources、retrieval_params、retrieval_steps，
    并查询关联的反馈记录（如有）。同时提取 citations 列表。
    """
    sources = [ChatSourceItem.model_validate(item) for item in load_message_sources(getattr(message, "sources_json", None))]
    retrieval_params = load_json_field(getattr(message, "retrieval_params_json", None))
    retrieval_steps = load_json_list(getattr(message, "retrieval_steps_json", None))
    feedback = get_feedback_for_message(message._sa_instance_state.session, message.id)
    citations = []
    uploaded_image_path = None
    uploaded_image_name = None
    if isinstance(retrieval_params, dict):
        uploaded_image_path = retrieval_params.get("uploaded_image_path")
        uploaded_image_name = retrieval_params.get("uploaded_image_name")
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
        uploaded_image_path=uploaded_image_path,
        uploaded_image_name=uploaded_image_name,
        sources=sources,
        citations=citations,
        retrieval_params=retrieval_params,
        retrieval_steps=retrieval_steps,
        feedback=AnswerFeedbackOut.model_validate(feedback) if feedback is not None else None,
        created_at=message.created_at,
    )


# ---- 会话管理端点 ----


@router.post("/api/chat/sessions", response_model=ChatSessionCreateResponse)
def create_chat_session(db: Session = Depends(get_db)) -> ChatSessionCreateResponse:
    """创建新的聊天会话。

    创建一条新的会话记录并返回其 ID 和时间戳。
    """
    session = create_session(db)
    return ChatSessionCreateResponse.model_validate(session)


@router.get("/api/chat/sessions", response_model=List[ChatSessionCreateResponse])
def list_chat_sessions(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[ChatSessionCreateResponse]:
    """列出聊天会话（分页）。

    按更新时间倒序返回会话列表，支持 limit/offset 分页参数。
    """
    sessions = list_sessions(db, limit=limit, offset=offset)
    return [ChatSessionCreateResponse.model_validate(session) for session in sessions]


@router.get("/api/chat/sessions/{session_id}", response_model=ChatSessionDetailResponse)
def get_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> ChatSessionDetailResponse:
    """获取单个会话详情（含全部消息）。

    返回会话的元信息及其下所有消息的完整内容、来源、引用等。
    会话不存在时抛出 HTTP 404。
    """
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
    """重命名聊天会话。

    更新会话标题并返回更新后的会话信息。会话不存在时抛出 HTTP 404。
    """
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
    """删除聊天会话。

    级联删除该会话下的所有消息。会话不存在时抛出 HTTP 404。
    """
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
    """提交对助手回答的反馈（评分 + 问题类型 + 评论）。

    查找指定消息 ID 的助手消息，向上回溯找到对应的用户查询，
    将反馈连同检索快照一起持久化，用于离线评估和改进。
    助手消息不存在时抛出 HTTP 404。
    """
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


# ---- RAG 聊天端点 ----


def _coerce_rag_chat_result(
    result: Any,
    *,
    has_uploaded_image: bool,
) -> tuple[str, List[dict], dict[str, Any]]:
    """将 adapter.rag_chat 的返回值统一为三元组 (answer, retrieved, intent)。

    兼容二元组和三元组两种返回格式。二元组时自动填充默认 intent 字典，
    包含 presentation_mode、execution_mode 等字段。
    """
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
    """构建流式响应的默认 intent 字典。

    当流式事件中未携带 intent 信息时，使用此默认值兜底。
    """
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
    resolved_chat_mode: str,
    source_scope: Optional[dict[str, list[str]]],
    intent: dict[str, Any],
    stream: bool,
    uploaded_image_path: Optional[str] = None,
    uploaded_image_name: Optional[str] = None,
) -> dict[str, Any]:
    """构建检索参数字典，用于持久化到消息记录中。

    汇总本次请求的所有参数（top_k、过滤阈值、execution_hint、chat_mode、
    source_scope）以及从 intent 中提取的分类器决策信息。
    """
    params = {
        "top_k": resolved_top_k,
        "has_image": image is not None,
        "query": query,
        "stream": stream,
        "enable_score_filter": resolved_enable_score_filter,
        "min_relevance_score": resolved_min_relevance_score,
        "chat_mode": resolved_chat_mode,
        "execution_hint": resolved_execution_hint,
        "source_scope": source_scope,
        "presentation_mode": intent.get("presentation_mode"),
        "execution_mode": intent.get("execution_mode"),
        "use_rag": intent.get("use_rag"),
        "classifier_reason": intent.get("reason"),
        "classifier_confidence": intent.get("confidence"),
    }
    if uploaded_image_path:
        params["uploaded_image_path"] = uploaded_image_path
    if uploaded_image_name:
        params["uploaded_image_name"] = uploaded_image_name
    return params


# ---- 响应构建器 ----


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
    """组装 ChatResponse 响应对象。

    将回答文本、检索结果、来源、引用、会话 ID、执行模式等打包为统一响应。
    根据配置决定是否附加耗时统计。
    """
    response = ChatResponse(
        answer=answer,
        results=_build_results(retrieved),
        sources=sources,
        session_id=session_id,
        chat_mode=str(intent.get("chat_mode", "default")),
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
    assistant_message_id: Optional[int] = None,
) -> dict[str, Any]:
    """构建 SSE 流式响应中的 results 事件 payload。

    包含检索结果、来源列表、引用、检索步骤、执行模式等完整信息，
    作为流结束时发送的最终汇总事件。
    """
    payload = {
        "type": "results",
        "results": [item.model_dump() for item in _build_results(retrieved)],
        "sources": [source.model_dump() for source in sources],
        "retrieval_steps": intent.get("retrieval_steps") or [],
        "chat_mode": str(intent.get("chat_mode", "default")),
        "presentation_mode": intent.get("presentation_mode", "rag_answer"),
        "execution_mode": intent.get("execution_mode", "multimodal_rag"),
        "use_rag": bool(intent.get("use_rag", True)),
        "has_uploaded_image": bool(intent.get("has_uploaded_image", False)),
        "citations": [citation.model_dump() for citation in citations],
        "assistant_message_id": assistant_message_id,
    }
    if settings.EXPOSE_TIMINGS_IN_API:
        payload["timings"] = TimingSummary.model_validate(collector.snapshot()).model_dump()
    return payload


def _safe_message_id(value: Any) -> Optional[int]:
    """安全地将值转换为正整数消息 ID。

    非数字或非正数时返回 None。
    """
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


# ---- 上下文准备 ----


async def _prepare_rag_chat_context(
    *,
    query: str,
    top_k: Optional[int],
    enable_score_filter: Optional[bool],
    min_relevance_score: Optional[float],
    execution_hint: Optional[str],
    chat_mode: Optional[str],
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
    str,
    Optional[dict[str, list[str]]],
    int,
    bool,
    Optional[float],
]:
    """准备 RAG 聊天请求的上下文（参数校验 + 会话加载 + 历史读取）。

    统一处理 JSON 和 SSE 两种端点的公共逻辑：
    1. 归一化 execution_hint、chat_mode、source_scope 参数
    2. 根据 chat_mode 解析 top_k 默认值（fast/default/expert 各有不同）
    3. 解析评分过滤阈值
    4. 创建 RequestTimingCollector 并记录元数据
    5. 加载或创建会话，读取最近 N 轮历史

    返回包含以上所有解析结果的元组。
    """
    resolved_execution_hint = _normalize_execution_hint(execution_hint)
    resolved_chat_mode = _normalize_chat_mode(chat_mode)
    source_scope = _parse_source_scope_json(source_scope_json)
    if top_k is not None:
        resolved_top_k = top_k
    elif resolved_chat_mode == "fast":
        resolved_top_k = settings.CHAT_FAST_DEFAULT_TOP_K
    elif resolved_chat_mode == "expert":
        resolved_top_k = settings.CHAT_EXPERT_DEFAULT_TOP_K
    else:
        resolved_top_k = settings.CHAT_DEFAULT_TOP_K
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
        chat_mode=resolved_chat_mode,
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
        resolved_chat_mode,
        source_scope,
        resolved_top_k,
        resolved_enable_score_filter,
        resolved_min_relevance_score,
    )


# ---- SSE 流式响应 ----


def _build_sse_chunk(payload: Any) -> str:
    """将 payload 序列化为 SSE 格式的单个事件字符串。

    格式为 `data: {json}\n\n`，符合 Server-Sent Events 规范。
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_progress_payload(
    *,
    phase: str,
    status: str,
    title: str,
    collector: RequestTimingCollector,
    detail: Optional[str] = None,
    chat_mode: str = "default",
    execution_mode: Optional[str] = None,
    use_rag: Optional[bool] = None,
    step_key: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """构建 SSE 进度事件 payload。

    用于向前端推送处理阶段的实时状态，包含阶段名（routing/retrieval/generate/complete）、
    状态（started/completed/failed）、标题、已耗时、执行模式等信息。
    前端据此展示进度指示器。
    """
    payload: dict[str, Any] = {
        "type": "progress",
        "phase": phase,
        "status": status,
        "title": title,
        "elapsed_ms": collector.snapshot().get("total_ms"),
        "chat_mode": chat_mode,
    }
    if detail:
        payload["detail"] = detail
    if execution_mode:
        payload["execution_mode"] = execution_mode
    if use_rag is not None:
        payload["use_rag"] = use_rag
    if step_key:
        payload["step_key"] = step_key
    if meta:
        payload["meta"] = meta
    return payload


def _normalize_stream_text_chunk(chunk: Any) -> str:
    """将流式文本块归一化为纯字符串。

    兼容三种输入格式：
    - 直接的字符串
    - LangChain AIMessageChunk（含 .content 属性）
    - 标准消息对象（含 .message.content 属性）
    不支持的类型抛出 TypeError。
    """
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
    resolved_chat_mode: str,
    source_scope: Optional[dict[str, list[str]]],
    resolved_top_k: int,
    resolved_enable_score_filter: bool,
    resolved_min_relevance_score: Optional[float],
    request_stage_name: str,
) -> StreamingResponse:
    """构建 SSE 流式响应的 StreamingResponse 对象。

    内部定义 `event_generator` 异步生成器，按以下顺序推送 SSE 事件：
    1. session 事件：告知前端会话 ID
    2. routing progress 事件：开始意图路由
    3. 内部 progress 事件：由 adapter 的 emit_progress 回调触发
    4. content 事件：LLM 逐 token 生成的文本片段
    5. complete progress 事件：处理完成
    6. results 事件：最终检索结果、来源、引用、耗时
    7. [DONE]：流结束标记

    异常时推送 error 事件并终止流。
    """
    adapter = get_langchain_adapter()

    async def event_generator():
        """SSE 事件流异步生成器。

        负责驱动整个流式响应生命周期：发送 session 事件、
        遍历 adapter 流、累积回答文本、持久化消息、
        最终发送 results 汇总和 [DONE] 结束标记。
        """
        with bind_timing_collector(collector), collector.stage(
            request_stage_name,
            meta={
                "top_k": resolved_top_k,
                "has_uploaded_image": image is not None,
                "enable_score_filter": resolved_enable_score_filter,
                "min_relevance_score": resolved_min_relevance_score,
                "chat_mode": resolved_chat_mode,
                "execution_hint": resolved_execution_hint,
                "source_scope": source_scope,
            },
        ):
            stream_aborted = False
            try:
                yield _build_sse_chunk({"type": "session", "session_id": session.id})

                full_answer = ""
                retrieved_docs: List[dict] = []
                final_intent: Optional[dict[str, Any]] = None
                progress_state: dict[str, Any] = {
                    "execution_mode": None,
                    "use_rag": None,
                }

                def emit_progress(
                    *,
                    phase: str,
                    status: str,
                    title: str,
                    detail: Optional[str] = None,
                    execution_mode: Optional[str] = None,
                    use_rag: Optional[bool] = None,
                    step_key: Optional[str] = None,
                    meta: Optional[dict[str, Any]] = None,
                ) -> str:
                    """构建并返回一个 SSE 进度事件字符串。

                    内部维护 progress_state 以跟踪 execution_mode 和 use_rag 的最新值，
                    新传入的值会覆盖旧值。返回值可直接 yield 给 SSE 流。
                    """
                    resolved_execution_mode = execution_mode or progress_state.get("execution_mode")
                    resolved_use_rag = progress_state.get("use_rag") if use_rag is None else use_rag
                    if execution_mode:
                        progress_state["execution_mode"] = execution_mode
                    if use_rag is not None:
                        progress_state["use_rag"] = use_rag
                    return _build_sse_chunk(
                        _build_progress_payload(
                            phase=phase,
                            status=status,
                            title=title,
                            detail=detail,
                            collector=collector,
                            chat_mode=resolved_chat_mode,
                            execution_mode=resolved_execution_mode,
                            use_rag=resolved_use_rag,
                            step_key=step_key,
                            meta=meta,
                        )
                    )

                yield emit_progress(
                    phase="routing",
                    status="started",
                    title="routing",
                    detail="Preparing chat route",
                    step_key="intent",
                    meta={"source_scope_enabled": bool(source_scope)},
                )

                uploaded_image_path: Optional[str] = None
                uploaded_image_name: Optional[str] = None
                if image is not None:
                    with collector.stage("chat_upload_persist"):
                        uploaded_image_path, uploaded_image_name = await _persist_uploaded_chat_image(image)

                try:
                    stream = adapter.rag_chat_stream(
                        query=query,
                        top_k=resolved_top_k,
                        image=image,
                        chat_history=history,
                        enable_score_filter=resolved_enable_score_filter,
                        min_relevance_score=resolved_min_relevance_score,
                        execution_hint=resolved_execution_hint,
                        chat_mode=resolved_chat_mode,
                        source_scope=source_scope,
                        emit_progress=True,
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
                    if isinstance(event, dict) and event.get("type") == "progress":
                        if event.get("execution_mode") or event.get("use_rag") is not None:
                            progress_state["execution_mode"] = event.get("execution_mode") or progress_state.get("execution_mode")
                            if event.get("use_rag") is not None:
                                progress_state["use_rag"] = bool(event.get("use_rag"))
                        yield _build_sse_chunk(event)
                        continue
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
                        progress_state["execution_mode"] = intent.get("execution_mode")
                        progress_state["use_rag"] = bool(intent.get("use_rag"))
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
                yield emit_progress(
                    phase="complete",
                    status="completed",
                    title="complete",
                    detail="Answer pipeline completed",
                    execution_mode=final_intent.get("execution_mode"),
                    use_rag=bool(final_intent.get("use_rag", True)),
                    step_key="generate",
                )
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
                    resolved_chat_mode=resolved_chat_mode,
                    source_scope=source_scope,
                    intent=final_intent,
                    stream=True,
                    uploaded_image_path=uploaded_image_path,
                    uploaded_image_name=uploaded_image_name,
                )
                sources = _normalize_chat_sources(retrieved_docs)
                citations = build_chat_citations(full_answer, sources)
                retrieval_steps = final_intent.get("retrieval_steps") or []
                assistant_message = None
                with collector.stage("chat_message_persist"):
                    add_message(db, session, "user", query, has_image=image is not None, retrieval_params=retrieval_params)
                    assistant_retrieval_params = {
                        **retrieval_params,
                        "citations": [citation.model_dump() for citation in citations],
                        "timings": TimingSummary.model_validate(collector.snapshot()).model_dump() if settings.EXPOSE_TIMINGS_IN_API else None,
                    }
                    assistant_message = add_message(
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
                            "chat_mode": resolved_chat_mode,
                            "retrieval_steps": retrieval_steps,
                            "has_uploaded_image": image is not None,
                        },
                        collector=collector,
                        assistant_message_id=_safe_message_id(
                            getattr(assistant_message, "id", None)
                        ),
                    )
                )
            except (asyncio.CancelledError, GeneratorExit):
                stream_aborted = True
                collector.set_metadata(stream_cancelled=True)
                raise
            except Exception as exc:
                yield emit_progress(
                    phase="complete",
                    status="failed",
                    title="complete",
                    detail=str(exc),
                    step_key="generate",
                )
                yield _build_sse_chunk({"type": "error", "detail": str(exc)})
            finally:
                if not stream_aborted:
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
    chat_mode: Optional[str] = Form(None),
    source_scope_json: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    stream: bool = Form(False),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
) -> Any:
    """RAG 聊天接口（支持 JSON 与 SSE 双模式）。

    POST `/api/rag/chat` 端点。根据 `stream` 参数决定响应模式：
    - stream=False：同步调用 adapter.rag_chat()，返回完整 ChatResponse
    - stream=True：调用 adapter.rag_chat_stream()，返回 SSE StreamingResponse

    支持多模态输入（可选 image），自动进行意图路由、双路检索和 RAG 回答生成。
    用户消息和助手回答均持久化到数据库会话中。
    """
    (
        collector,
        session,
        history,
        resolved_execution_hint,
        resolved_chat_mode,
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
        chat_mode=chat_mode,
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
            resolved_chat_mode=resolved_chat_mode,
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
                "chat_mode": resolved_chat_mode,
                "execution_hint": resolved_execution_hint,
                "source_scope": source_scope,
            },
        ):
            adapter = get_langchain_adapter()
            uploaded_image_path: Optional[str] = None
            uploaded_image_name: Optional[str] = None
            if image is not None:
                with collector.stage("chat_upload_persist"):
                    uploaded_image_path, uploaded_image_name = await _persist_uploaded_chat_image(image)
            result = await adapter.rag_chat(
                query=query,
                top_k=resolved_top_k,
                image=image,
                chat_history=history,
                enable_score_filter=resolved_enable_score_filter,
                min_relevance_score=resolved_min_relevance_score,
                execution_hint=resolved_execution_hint,
                chat_mode=resolved_chat_mode,
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
                resolved_chat_mode=resolved_chat_mode,
                source_scope=source_scope,
                intent=intent,
                stream=False,
                uploaded_image_path=uploaded_image_path,
                uploaded_image_name=uploaded_image_name,
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
                chat_mode=resolved_chat_mode,
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
    chat_mode: Optional[str] = Form(None),
    source_scope_json: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """RAG 聊天流式接口（SSE）。

    POST `/api/rag/chat/stream` 端点，始终返回 SSE StreamingResponse。

    流式事件序列：
    1. `session`：会话 ID
    2. `progress`：routing / retrieval / generate / complete 各阶段状态
    3. `content`：LLM 逐 token 生成的文本片段
    4. `results`：最终检索结果、来源、引用、耗时
    5. `[DONE]`：流结束标记

    适合需要实时展示生成进度的前端场景。
    """
    (
        collector,
        session,
        history,
        resolved_execution_hint,
        resolved_chat_mode,
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
        chat_mode=chat_mode,
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
        resolved_chat_mode=resolved_chat_mode,
        source_scope=source_scope,
        resolved_top_k=resolved_top_k,
        resolved_enable_score_filter=resolved_enable_score_filter,
        resolved_min_relevance_score=resolved_min_relevance_score,
        request_stage_name="rag_chat_stream_total",
    )
