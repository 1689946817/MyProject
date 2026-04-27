"""
LangChain 适配器模块

该模块提供与现有系统的适配层，包括：
- 与现有 API 路由的适配
- 与现有数据库模型的适配
- 与现有业务逻辑的适配

确保 LangChain 重构后的系统与现有前端、数据库、文件存储等无缝集成。
"""
import base64
import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Literal, Optional, Tuple, Union

from fastapi import UploadFile
from langchain_core.documents import Document as LCDoc
from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from app.data.doc_models import DocumentRecord
from app.data.database import SessionLocal
from app.data.models import ImageRecord
from app.data.storage import BASE_STORAGE_DIR, DOC_STORAGE_DIR, get_image_path, get_doc_path
from app.application.knowledge_management import (
    ensure_knowledge_management_columns,
    get_document_image_records,
    load_tags,
    load_json_dict,
    safe_unlink,
)
from app.core.config import settings
from app.core.timing import get_current_timing_collector, timing_stage
from app.langchain_integration.agentic_rag import (
    _rule_based_intent,
    classify_chat_intent,
    prepare_agentic_multimodal_rag_context,
    run_agentic_multimodal_rag,
)
from app.langchain_integration.chains import (
    get_image_description_chain,
    get_rag_chain,
    ImageDescriptionChain,
    RAGChain,
)
from app.langchain_integration.doc_parser import (
    build_pdf_text_chunks,
    extract_pdf_text_documents,
    extract_pdf_visual_assets,
    normalize_mineru_markdown_for_chunking,
)
from app.langchain_integration.mineru_client import MinerUClient, MinerUParseResult
from app.langchain_integration.models import (
    build_image_data_url,
    get_multimodal_chat_model,
    get_primary_text_chat_model,
    guess_image_mime_type,
)
from app.langchain_integration.retrievers import get_multimodal_retriever
from app.langchain_integration.vectorstores import get_vector_store, get_document_vector_store

logger = logging.getLogger(__name__)
_TRANSIENT_EXTERNAL_ERROR_MARKERS = (
    "unexpected_eof_while_reading",
    "eof occurred in violation of protocol",
    "connection reset",
    "all connection attempts failed",
    "temporarily unavailable",
    "read timed out",
    "timed out",
    "ssl",
)
ChatMode = Literal["fast", "default", "expert"]
StreamProgressEvent = Dict[str, Any]
StreamChunkEvent = Tuple[Any, List[Dict[str, Any]], Optional[Dict[str, Any]]]
StreamEvent = Union[StreamProgressEvent, StreamChunkEvent]


class LangChainAdapter:
    """
    LangChain 适配器

    提供与现有系统的适配接口，包括：
    - 图像上传处理（替代 description_service）
    - 双路检索（替代 dispatcher）
    - RAG 问答（替代 rag_engine）

    保持与现有 API 路由的接口兼容，内部使用 LangChain 组件实现。
    """

    def __init__(
        self,
        image_description_chain: Optional[ImageDescriptionChain] = None,
        rag_chain: Optional[RAGChain] = None,
    ):
        """
        初始化适配器

        Args:
            image_description_chain: 图像描述 Chain，默认使用全局实例
            rag_chain: RAG Chain，默认使用全局实例
        """
        self.image_description_chain = image_description_chain or get_image_description_chain()
        self.rag_chain = rag_chain or get_rag_chain()
        self.vector_store = get_vector_store()
        self.retriever = get_multimodal_retriever()
        self.document_vector_store = get_document_vector_store()

    def _build_chat_mode_profile(self, chat_mode: ChatMode) -> Optional[Dict[str, Any]]:
        if chat_mode == "fast":
            return {
                "chat_mode": "fast",
                "enable_query_rewrite": not settings.CHAT_FAST_DISABLE_QUERY_REWRITE,
                "query_rewrite_count": None,
                "enable_rerank": not settings.CHAT_FAST_DISABLE_RERANK,
                "enable_context_compression": not settings.CHAT_FAST_DISABLE_CONTEXT_COMPRESSION,
                "candidate_k": None,
                "image_fast_path": True,
                "force_true_streaming": settings.CHAT_FAST_FORCE_TRUE_STREAMING,
            }
        if chat_mode == "expert":
            return {
                "chat_mode": "expert",
                "enable_query_rewrite": settings.CHAT_EXPERT_FORCE_QUERY_REWRITE,
                "query_rewrite_count": settings.CHAT_EXPERT_QUERY_MULTI_COUNT,
                "enable_rerank": settings.CHAT_EXPERT_FORCE_RERANK,
                "enable_context_compression": settings.CHAT_EXPERT_FORCE_CONTEXT_COMPRESSION,
                "candidate_k": settings.CHAT_EXPERT_RERANK_CANDIDATE_K,
                "image_fast_path": False,
                "force_true_streaming": settings.CHAT_EXPERT_FORCE_TRUE_STREAMING,
            }
        return None

    @staticmethod
    def _build_progress_event(
        *,
        phase: str,
        status: str,
        title: str,
        chat_mode: ChatMode,
        execution_mode: Optional[str] = None,
        use_rag: Optional[bool] = None,
        step_key: Optional[str] = None,
        detail: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> StreamProgressEvent:
        payload: StreamProgressEvent = {
            "type": "progress",
            "phase": phase,
            "status": status,
            "title": title,
            "chat_mode": chat_mode,
        }
        if execution_mode:
            payload["execution_mode"] = execution_mode
        if use_rag is not None:
            payload["use_rag"] = use_rag
        if step_key:
            payload["step_key"] = step_key
        if detail:
            payload["detail"] = detail
        if meta:
            payload["meta"] = meta
        return payload

    @staticmethod
    def _progress_meta(
        *,
        source_scope: Optional[Dict[str, List[str]]] = None,
        query_rewrite_enabled: Optional[bool] = None,
        rerank_enabled: Optional[bool] = None,
        compression_enabled: Optional[bool] = None,
        agentic_enabled: Optional[bool] = None,
        retrieved_candidates: Optional[int] = None,
        generation_started: Optional[bool] = None,
        retry_used: Optional[bool] = None,
        classifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        if source_scope is not None:
            meta["source_scope_enabled"] = bool(source_scope)
        if query_rewrite_enabled is not None:
            meta["query_rewrite_enabled"] = query_rewrite_enabled
        if rerank_enabled is not None:
            meta["rerank_enabled"] = rerank_enabled
        if compression_enabled is not None:
            meta["compression_enabled"] = compression_enabled
        if agentic_enabled is not None:
            meta["agentic_enabled"] = agentic_enabled
        if retrieved_candidates is not None:
            meta["retrieved_candidates"] = retrieved_candidates
        if generation_started is not None:
            meta["generation_started"] = generation_started
        if retry_used is not None:
            meta["retry_used"] = retry_used
        if classifier:
            meta["classifier"] = classifier
        return meta

    @staticmethod
    def _compute_content_hash(contents: bytes) -> str:
        return hashlib.sha256(contents).hexdigest()

    @staticmethod
    def _next_document_version(db: Session, logical_asset_id: str) -> int:
        existing = (
            db.query(DocumentRecord)
            .filter(DocumentRecord.logical_asset_id == logical_asset_id)
            .order_by(DocumentRecord.version_number.desc())
            .first()
        )
        if existing is None:
            return 1
        return int(getattr(existing, "version_number", 1) or 1) + 1

    @staticmethod
    def _next_image_version(db: Session, logical_asset_id: str) -> int:
        existing = (
            db.query(ImageRecord)
            .filter(ImageRecord.logical_asset_id == logical_asset_id)
            .order_by(ImageRecord.version_number.desc())
            .first()
        )
        if existing is None:
            return 1
        return int(getattr(existing, "version_number", 1) or 1) + 1

    async def process_image_upload(
        self,
        db: Session,
        file: UploadFile,
        split: str = "custom",
        source_dataset: Optional[str] = None,
        logical_asset_id: Optional[str] = None,
    ) -> Tuple[ImageRecord, str, bool, Optional[str]]:
        """
        处理单个图像上传

        替代原有的 description_service.process_image_uploads 功能。

        Args:
            db: 数据库会话
            file: 上传的图像文件
            split: 数据集划分（train/val/test/custom）
            source_dataset: 来源数据集名称

        Returns:
            Tuple[ImageRecord, str]: (图像记录, 生成的描述)
        """
        import uuid

        with timing_stage("process_image_upload", meta={"split": split, "filename": file.filename}):
            image_id = str(uuid.uuid4())

            with timing_stage("upload_file_read"):
                contents = await file.read()
            content_hash = self._compute_content_hash(contents)

            filename = file.filename or "image.jpg"
            ext = os.path.splitext(filename)[1].lower()
            if not ext:
                ext = ".jpg"

            existing = (
                db.query(ImageRecord)
                .filter(ImageRecord.content_hash == content_hash, ImageRecord.is_latest.is_(True))
                .first()
            )
            if existing is not None:
                return existing, existing.generated_description or "", True, existing.id

            storage_path = str(get_image_path(image_id, split))
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)

            with timing_stage("upload_file_save"):
                with open(storage_path, "wb") as f:
                    f.write(contents)

            resolved_logical_asset_id = logical_asset_id or image_id
            version_number = self._next_image_version(db, resolved_logical_asset_id) if logical_asset_id else 1
            if logical_asset_id:
                db.query(ImageRecord).filter(
                    ImageRecord.logical_asset_id == resolved_logical_asset_id,
                    ImageRecord.is_latest.is_(True),
                ).update({"is_latest": False})

            record = ImageRecord(
                id=image_id,
                file_path=storage_path,
                source_dataset=source_dataset,
                title=os.path.splitext(filename)[0],
                status="Processing",
                content_hash=content_hash,
                logical_asset_id=resolved_logical_asset_id,
                version_number=version_number,
                is_latest=True,
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            try:
                b64_image = base64.b64encode(contents).decode("utf-8")
                with timing_stage("image_description_generation"):
                    description = await self.image_description_chain.ainvoke({
                        "image_b64": b64_image,
                    })

                record.generated_description = description
                record.status = "Completed"
                db.commit()
                db.refresh(record)

                with timing_stage("image_vector_upsert"):
                    self.vector_store.upsert_image_description(
                        doc_id=image_id,
                        text=description,
                        metadata={
                            "id": image_id,
                            "file_path": storage_path,
                            "filename": filename,
                            "split": split,
                            "source_dataset": source_dataset,
                            "title": os.path.splitext(filename)[0],
                            "tags": [],
                            "enabled": True,
                            "parent_doc_enabled": True,
                        },
                    )

                with timing_stage("bm25_incremental_update"):
                    self._bm25_add_document(image_id, description)

                return record, description, False, None

            except Exception as e:
                record.status = "Failed"
                db.commit()
                raise e

    async def process_image_uploads(
        self,
        db: Session,
        files: List[UploadFile],
        split: str = "custom",
        source_dataset: Optional[str] = None,
    ) -> List[Tuple[ImageRecord, str, bool, Optional[str]]]:
        """
        处理多个图像上传

        替代原有的 description_service.process_image_uploads 功能。

        Args:
            db: 数据库会话
            files: 上传的图像文件列表
            split: 数据集划分
            source_dataset: 来源数据集名称

        Returns:
            List[Tuple[ImageRecord, str]]: (图像记录, 描述) 列表
        """
        with timing_stage("process_image_uploads", meta={"file_count": len(files), "split": split}):
            results = []
            for file in files:
                result = await self.process_image_upload(
                    db=db,
                    file=file,
                    split=split,
                    source_dataset=source_dataset,
                )
                results.append(result)
            return results

    async def text_to_image_search(
        self,
        query: str,
        top_k: int = 10,
        fast: bool = False,
        enable_score_filter: bool = False,
        min_relevance_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        文本到图像检索

        替代原有的 dispatcher.text_to_image_search 功能。

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            List[Dict[str, Any]]: 检索结果列表
        """
        with timing_stage(
            "adapter_text_to_image_search",
            meta={
                "top_k": top_k,
                "fast_path": fast,
                "enable_score_filter": enable_score_filter,
                "min_relevance_score": min_relevance_score,
            },
        ):
            documents = await self.retriever.text_to_image_search(
                query,
                top_k=top_k,
                fast=fast,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
            )

        # 转换为字典格式
        results = []
        for doc in documents:
            results.append({
                "id": doc.metadata.get("id", ""),
                "document": doc.page_content,
                "metadata": doc.metadata,
                "score": doc.metadata.get("score", 0.0),
                "relevance_score": doc.metadata.get("relevance_score"),
                "score_source": doc.metadata.get("score_source"),
            })

        return results

    async def image_to_image_search(
        self,
        file: UploadFile,
        top_k: int = 10,
        fast: bool = False,
        enable_score_filter: bool = False,
        min_relevance_score: Optional[float] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        图像到图像检索

        替代原有的 dispatcher.image_to_image_search 功能。

        Args:
            file: 上传的图像文件
            top_k: 返回结果数量

        Returns:
            Tuple[List[Dict], str]: (检索结果列表, 生成的描述)
        """
        with timing_stage(
            "adapter_image_to_image_search",
            meta={
                "top_k": top_k,
                "fast_path": fast,
                "enable_score_filter": enable_score_filter,
                "min_relevance_score": min_relevance_score,
            },
        ):
            documents, description = await self.retriever.image_to_image_search(
                file,
                top_k=top_k,
                fast=fast,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
            )

        # 转换为字典格式
        results = []
        for doc in documents:
            results.append({
                "id": doc.metadata.get("id", ""),
                "document": doc.page_content,
                "metadata": doc.metadata,
                "score": doc.metadata.get("score", 0.0),
                "relevance_score": doc.metadata.get("relevance_score"),
                "score_source": doc.metadata.get("score_source"),
            })

        return results, description

    async def rag_chat(
        self,
        query: str,
        top_k: int = 5,
        image: Optional[UploadFile] = None,
        chat_history: Optional[List[Tuple[str, str]]] = None,
        enable_score_filter: bool = False,
        min_relevance_score: Optional[float] = None,
        execution_hint: Optional[str] = None,
        source_scope: Optional[Dict[str, List[str]]] = None,
        chat_mode: ChatMode = "default",
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        RAG 问答（支持多轮对话历史 + Agentic RAG）
        """
        with timing_stage(
            "adapter_rag_chat",
            meta={"top_k": top_k, "has_uploaded_image": image is not None, "chat_mode": chat_mode},
        ):
            from app.core.config import settings
            if chat_mode == "fast":
                return await self._run_fast_chat(
                    query=query,
                    top_k=top_k,
                    image=image,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                    source_scope=source_scope,
                )
            if chat_mode == "expert":
                return await self._run_expert_chat(
                    query=query,
                    top_k=top_k,
                    image=image,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                    source_scope=source_scope,
                )
            if settings.AGENTIC_RAG_ENABLED:
                return await self._run_agentic_chat(
                    query=query,
                    top_k=top_k,
                    image=image,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                    execution_hint=execution_hint,
                    source_scope=source_scope,
                )

            if source_scope or execution_hint:
                return await self._run_scoped_chat(
                    query=query,
                    top_k=top_k,
                    image=image,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                    execution_hint=execution_hint or "multimodal_rag",
                    source_scope=source_scope,
                )

            if image is not None:
                answer, documents = await self.rag_chain.ainvoke_with_image(
                    query,
                    image,
                    top_k=top_k,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                )
                intent = self._build_default_intent(image is not None)
                intent["retrieval_steps"] = self._build_retrieval_steps(
                    query=query,
                    top_k=top_k,
                    execution_mode=intent["execution_mode"],
                    presentation_mode=intent["presentation_mode"],
                    use_rag=bool(intent["use_rag"]),
                    documents=documents,
                    has_uploaded_image=True,
                    classifier_reason=str(intent.get("reason", "")),
                )
                return answer, documents, intent

            answer, documents = await self.rag_chain.ainvoke(
                {
                    "query": query,
                    "chat_history": chat_history or [],
                    "top_k": top_k,
                    "enable_score_filter": enable_score_filter,
                    "min_relevance_score": min_relevance_score,
                }
            )
            intent = self._build_default_intent(image is not None)
            intent["retrieval_steps"] = self._build_retrieval_steps(
                query=query,
                top_k=top_k,
                execution_mode=intent["execution_mode"],
                presentation_mode=intent["presentation_mode"],
                use_rag=bool(intent["use_rag"]),
                documents=documents,
                has_uploaded_image=False,
                classifier_reason=str(intent.get("reason", "")),
            )
            return answer, documents, intent

    async def rag_chat_stream(
        self,
        query: str,
        top_k: int = 5,
        image: Optional[UploadFile] = None,
        chat_history: Optional[List[Tuple[str, str]]] = None,
        enable_score_filter: bool = False,
        min_relevance_score: Optional[float] = None,
        execution_hint: Optional[str] = None,
        source_scope: Optional[Dict[str, List[str]]] = None,
        chat_mode: ChatMode = "default",
        emit_progress: bool = False,
    ):
        """
        RAG 问答流式版本。
        """
        from app.core.config import settings
        default_query_rewrite_enabled = settings.QUERY_REWRITE_ENABLED
        default_rerank_enabled = settings.RERANK_TOP_K > 0 and settings.RERANK_CANDIDATE_K > 0
        default_compression_enabled = settings.CONTEXT_COMPRESSION_ENABLED

        if chat_mode in {"fast", "expert"}:
            async for event in self._stream_chat_mode_response(
                query=query,
                top_k=top_k,
                image=image,
                chat_history=chat_history,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
                source_scope=source_scope,
                chat_mode=chat_mode,
                emit_progress=emit_progress,
            ):
                yield event
            return

        if source_scope or execution_hint:
            execution_mode = execution_hint or "multimodal_rag"
            intent = self._build_forced_intent(execution_mode, image is not None)
            async for event in self._stream_intent_chat(
                intent=intent,
                query=query,
                top_k=top_k,
                image=image,
                chat_history=chat_history,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
                source_scope=source_scope,
                retrieval_profile=None,
                force_agentic_rag=False,
                chat_mode=chat_mode,
                emit_progress=emit_progress,
            ):
                yield event
            return

        if settings.AGENTIC_RAG_ENABLED:
            intent = await classify_chat_intent(query=query, has_uploaded_image=image is not None)
            collector = get_current_timing_collector()
            if collector is not None:
                collector.set_metadata(
                    execution_mode=intent["execution_mode"],
                    presentation_mode=intent["presentation_mode"],
                )
            if emit_progress:
                yield self._build_progress_event(
                    phase="routing",
                    status="completed",
                    title="routing",
                    chat_mode=chat_mode,
                    execution_mode=intent["execution_mode"],
                    use_rag=bool(intent.get("use_rag", True)),
                    step_key="intent",
                    detail="Routing decided by classifier",
                    meta=self._progress_meta(
                        source_scope=source_scope,
                        classifier="llm",
                        agentic_enabled=intent["execution_mode"] == "multimodal_rag" and image is None,
                    ),
                )

            if intent["execution_mode"] == "multimodal_rag" and image is None:
                if emit_progress:
                    if default_query_rewrite_enabled:
                        yield self._build_progress_event(
                            phase="rewrite",
                            status="started",
                            title="rewrite",
                            chat_mode=chat_mode,
                            execution_mode=intent["execution_mode"],
                            use_rag=True,
                            step_key="query",
                            meta=self._progress_meta(query_rewrite_enabled=True),
                        )
                    else:
                        yield self._build_progress_event(
                            phase="rewrite",
                            status="skipped",
                            title="rewrite",
                            chat_mode=chat_mode,
                            execution_mode=intent["execution_mode"],
                            use_rag=True,
                            step_key="query",
                            meta=self._progress_meta(query_rewrite_enabled=False),
                        )
                    yield self._build_progress_event(
                        phase="retrieve",
                        status="started",
                        title="retrieve",
                        chat_mode=chat_mode,
                        execution_mode=intent["execution_mode"],
                        use_rag=True,
                        step_key="retrieve",
                    )
                    yield self._build_progress_event(
                        phase="rerank",
                        status="started" if default_rerank_enabled else "skipped",
                        title="rerank",
                        chat_mode=chat_mode,
                        execution_mode=intent["execution_mode"],
                        use_rag=True,
                        step_key="retrieve",
                        meta=self._progress_meta(rerank_enabled=default_rerank_enabled),
                    )
                    yield self._build_progress_event(
                        phase="compress",
                        status="started" if default_compression_enabled else "skipped",
                        title="compress",
                        chat_mode=chat_mode,
                        execution_mode=intent["execution_mode"],
                        use_rag=True,
                        step_key="retrieve",
                        meta=self._progress_meta(compression_enabled=default_compression_enabled),
                    )
                    yield self._build_progress_event(
                        phase="agentic",
                        status="started",
                        title="agentic",
                        chat_mode=chat_mode,
                        execution_mode=intent["execution_mode"],
                        use_rag=True,
                        step_key="retrieve",
                        meta=self._progress_meta(agentic_enabled=True),
                    )
                _final_state, docs, text_chunks, retrieval_steps = await prepare_agentic_multimodal_rag_context(
                    query=query,
                    top_k=top_k,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                    rag_chain=self.rag_chain,
                    retriever=self.retriever,
                    doc_vector_store=self.document_vector_store,
                    execution_mode=intent["execution_mode"],
                    presentation_mode=intent["presentation_mode"],
                    classifier_reason=str(intent.get("reason", "")),
                    has_uploaded_image=False,
                )
                intent["retrieval_steps"] = retrieval_steps
                if emit_progress:
                    if default_query_rewrite_enabled:
                        yield self._build_progress_event(
                            phase="rewrite",
                            status="completed",
                            title="rewrite",
                            chat_mode=chat_mode,
                            execution_mode=intent["execution_mode"],
                            use_rag=True,
                            step_key="query",
                            meta=self._progress_meta(query_rewrite_enabled=True),
                        )
                    yield self._build_progress_event(
                        phase="retrieve",
                        status="completed",
                        title="retrieve",
                        chat_mode=chat_mode,
                        execution_mode=intent["execution_mode"],
                        use_rag=True,
                        step_key="retrieve",
                        meta=self._progress_meta(retrieved_candidates=len(docs) + len(text_chunks)),
                    )
                    if default_rerank_enabled:
                        yield self._build_progress_event(
                            phase="rerank",
                            status="completed",
                            title="rerank",
                            chat_mode=chat_mode,
                            execution_mode=intent["execution_mode"],
                            use_rag=True,
                            step_key="retrieve",
                            meta=self._progress_meta(rerank_enabled=True),
                        )
                    if default_compression_enabled:
                        yield self._build_progress_event(
                            phase="compress",
                            status="completed",
                            title="compress",
                            chat_mode=chat_mode,
                            execution_mode=intent["execution_mode"],
                            use_rag=True,
                            step_key="retrieve",
                            meta=self._progress_meta(compression_enabled=True),
                        )
                    yield self._build_progress_event(
                        phase="agentic",
                        status="completed",
                        title="agentic",
                        chat_mode=chat_mode,
                        execution_mode=intent["execution_mode"],
                        use_rag=True,
                        step_key="retrieve",
                        meta=self._progress_meta(agentic_enabled=True),
                    )
                    yield self._build_progress_event(
                        phase="generate",
                        status="started",
                        title="generate",
                        chat_mode=chat_mode,
                        execution_mode=intent["execution_mode"],
                        use_rag=True,
                        step_key="generate",
                        meta=self._progress_meta(generation_started=True),
                    )
                async for chunk in self.rag_chain.astream_from_context(
                    query=query,
                    documents=docs,
                    text_chunks=text_chunks,
                    chat_history=chat_history or [],
                ):
                    yield chunk, docs, intent
                return

            if intent["execution_mode"] == "direct_llm":
                async for event in self._stream_intent_chat(
                    intent=intent,
                    query=query,
                    top_k=top_k,
                    image=image,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                    source_scope=source_scope,
                    retrieval_profile=None,
                    force_agentic_rag=False,
                    chat_mode=chat_mode,
                    emit_progress=emit_progress,
                ):
                    yield event
                return

            if intent["execution_mode"] == "uploaded_image_qa":
                async for event in self._stream_intent_chat(
                    intent=intent,
                    query=query,
                    top_k=top_k,
                    image=image,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                    source_scope=source_scope,
                    retrieval_profile=None,
                    force_agentic_rag=False,
                    chat_mode=chat_mode,
                    emit_progress=emit_progress,
                ):
                    yield event
                return

            # Non-RAG or model-specific agentic modes keep replayed streaming for compatibility.
            if emit_progress:
                yield self._build_progress_event(
                    phase="generate",
                    status="started",
                    title="generate",
                    chat_mode=chat_mode,
                    execution_mode=intent["execution_mode"],
                    use_rag=bool(intent.get("use_rag", True)),
                    step_key="generate",
                    meta=self._progress_meta(generation_started=True),
                )
            answer, docs, _intent = await self._run_agentic_chat(
                query=query,
                top_k=top_k,
                image=image,
                chat_history=chat_history,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
                execution_hint=execution_hint,
                source_scope=source_scope,
            )
            for ch in self._iter_answer_chunks(answer):
                yield ch, docs, _intent
            return

        if image is not None:
            if emit_progress:
                yield self._build_progress_event(
                    phase="routing",
                    status="completed",
                    title="routing",
                    chat_mode=chat_mode,
                    execution_mode="multimodal_rag",
                    use_rag=True,
                    step_key="intent",
                    detail="Default multimodal RAG route",
                    meta=self._progress_meta(source_scope=source_scope, classifier="default"),
                )
                yield self._build_progress_event(
                    phase="retrieve",
                    status="started",
                    title="retrieve",
                    chat_mode=chat_mode,
                    execution_mode="multimodal_rag",
                    use_rag=True,
                    step_key="retrieve",
                )
                yield self._build_progress_event(
                    phase="generate",
                    status="started",
                    title="generate",
                    chat_mode=chat_mode,
                    execution_mode="multimodal_rag",
                    use_rag=True,
                    step_key="generate",
                    meta=self._progress_meta(generation_started=True),
                )
            async for chunk, docs in self.rag_chain.astream_with_image(
                query=query,
                image=image,
                top_k=top_k,
                chat_history=chat_history,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
            ):
                yield chunk, docs, None
            return

        if emit_progress:
            yield self._build_progress_event(
                phase="routing",
                status="completed",
                title="routing",
                chat_mode=chat_mode,
                execution_mode="multimodal_rag",
                use_rag=True,
                step_key="intent",
                detail="Default RAG route",
                meta=self._progress_meta(source_scope=source_scope, classifier="default"),
            )
            yield self._build_progress_event(
                phase="retrieve",
                status="started",
                title="retrieve",
                chat_mode=chat_mode,
                execution_mode="multimodal_rag",
                use_rag=True,
                step_key="retrieve",
            )
            yield self._build_progress_event(
                phase="generate",
                status="started",
                title="generate",
                chat_mode=chat_mode,
                execution_mode="multimodal_rag",
                use_rag=True,
                step_key="generate",
                meta=self._progress_meta(generation_started=True),
            )
        async for chunk, docs in self.rag_chain.astream(
            {
                "query": query,
                "chat_history": chat_history or [],
                "top_k": top_k,
                "enable_score_filter": enable_score_filter,
                "min_relevance_score": min_relevance_score,
            }
        ):
            yield chunk, docs, None

    async def _run_agentic_chat(
        self,
        query: str,
        top_k: int,
        image: Optional[UploadFile],
        chat_history: Optional[List[Tuple[str, str]]],
        enable_score_filter: bool,
        min_relevance_score: Optional[float],
        execution_hint: Optional[str] = None,
        source_scope: Optional[Dict[str, List[str]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """执行带智能意图识别的 Agentic Chat 核心流程。"""
        if source_scope or execution_hint:
            return await self._run_scoped_chat(
                query=query,
                top_k=top_k,
                image=image,
                chat_history=chat_history,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
                execution_hint=execution_hint or "multimodal_rag",
                source_scope=source_scope,
            )

        intent = await classify_chat_intent(query=query, has_uploaded_image=image is not None)
        collector = get_current_timing_collector()
        if collector is not None:
            collector.set_metadata(
                execution_mode=intent["execution_mode"],
                presentation_mode=intent["presentation_mode"],
            )
        return await self._run_intent_chat(
            intent=intent,
            query=query,
            top_k=top_k,
            image=image,
            chat_history=chat_history,
            enable_score_filter=enable_score_filter,
            min_relevance_score=min_relevance_score,
            force_agentic_rag=False,
        )

    async def _run_fast_chat(
        self,
        *,
        query: str,
        top_k: int,
        image: Optional[UploadFile],
        chat_history: Optional[List[Tuple[str, str]]],
        enable_score_filter: bool,
        min_relevance_score: Optional[float],
        source_scope: Optional[Dict[str, List[str]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        retrieval_profile = self._build_chat_mode_profile("fast")
        intent = _rule_based_intent(query, image is not None)
        if intent is None:
            if image is not None:
                intent = self._build_forced_intent("uploaded_image_qa", True)
                intent["reason"] = "fast_mode_uploaded_image_fallback"
            elif source_scope:
                intent = self._build_forced_intent("multimodal_rag", False)
                intent["reason"] = "fast_mode_scoped_rag_fallback"
            else:
                intent = self._build_forced_intent("direct_llm", False)
                intent["reason"] = "fast_mode_direct_fallback"

        collector = get_current_timing_collector()
        if collector is not None:
            collector.set_metadata(
                execution_mode=intent["execution_mode"],
                presentation_mode=intent["presentation_mode"],
            )

        return await self._run_intent_chat(
            intent=intent,
            query=query,
            top_k=top_k,
            image=image,
            chat_history=chat_history,
            enable_score_filter=enable_score_filter,
            min_relevance_score=min_relevance_score,
            source_scope=source_scope,
            force_agentic_rag=False,
            retrieval_profile=retrieval_profile,
        )

    async def _run_expert_chat(
        self,
        *,
        query: str,
        top_k: int,
        image: Optional[UploadFile],
        chat_history: Optional[List[Tuple[str, str]]],
        enable_score_filter: bool,
        min_relevance_score: Optional[float],
        source_scope: Optional[Dict[str, List[str]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        retrieval_profile = self._build_chat_mode_profile("expert")
        intent = await classify_chat_intent(
            query=query,
            has_uploaded_image=image is not None,
            mode="expert",
        )
        collector = get_current_timing_collector()
        if collector is not None:
            collector.set_metadata(
                execution_mode=intent["execution_mode"],
                presentation_mode=intent["presentation_mode"],
            )
        return await self._run_intent_chat(
            intent=intent,
            query=query,
            top_k=top_k,
            image=image,
            chat_history=chat_history,
            enable_score_filter=enable_score_filter,
            min_relevance_score=min_relevance_score,
            source_scope=source_scope,
            force_agentic_rag=settings.CHAT_EXPERT_FORCE_AGENTIC_RAG,
            retrieval_profile=retrieval_profile,
        )

    async def _run_intent_chat(
        self,
        *,
        intent: Dict[str, Any],
        query: str,
        top_k: int,
        image: Optional[UploadFile],
        chat_history: Optional[List[Tuple[str, str]]],
        enable_score_filter: bool,
        min_relevance_score: Optional[float],
        source_scope: Optional[Dict[str, List[str]]] = None,
        force_agentic_rag: bool = False,
        retrieval_profile: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        execution_mode = intent["execution_mode"]

        if retrieval_profile and execution_mode in {"image_similarity", "image_grounded_answer", "multimodal_rag"}:
            if execution_mode == "multimodal_rag" and force_agentic_rag and image is None and not source_scope:
                answer, documents, retrieval_steps = await run_agentic_multimodal_rag(
                    query=query,
                    top_k=top_k,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                    rag_chain=self.rag_chain,
                    retriever=self.retriever,
                    doc_vector_store=self.document_vector_store,
                    execution_mode=execution_mode,
                    presentation_mode=intent["presentation_mode"],
                    classifier_reason=str(intent.get("reason", "")),
                    has_uploaded_image=False,
                    retrieval_profile=retrieval_profile,
                )
                intent["retrieval_steps"] = retrieval_steps
                return answer, documents, intent
            return await self._run_scoped_chat(
                query=query,
                top_k=top_k,
                image=image,
                chat_history=chat_history,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
                execution_hint=execution_mode,
                source_scope=source_scope,
                retrieval_profile=retrieval_profile,
            )

        if source_scope and execution_mode in {"multimodal_rag", "image_similarity", "image_grounded_answer"}:
            return await self._run_scoped_chat(
                query=query,
                top_k=top_k,
                image=image,
                chat_history=chat_history,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
                execution_hint=execution_mode,
                source_scope=source_scope,
                retrieval_profile=retrieval_profile,
            )

        if execution_mode == "direct_llm":
            answer = await self._answer_directly(query=query, chat_history=chat_history)
            intent["retrieval_steps"] = self._build_retrieval_steps(
                query=query,
                top_k=top_k,
                execution_mode=execution_mode,
                presentation_mode=intent["presentation_mode"],
                use_rag=bool(intent["use_rag"]),
                documents=[],
                has_uploaded_image=image is not None,
                classifier_reason=str(intent.get("reason", "")),
            )
            return answer, [], intent

        if execution_mode == "uploaded_image_qa":
            if image is None:
                answer = await self._answer_directly(query=query, chat_history=chat_history)
                fallback_intent = {
                    **intent,
                    "execution_mode": "direct_llm",
                    "presentation_mode": "direct_answer",
                    "use_rag": False,
                    "wants_images": False,
                    "reason": "uploaded_image_missing_fallback_to_direct",
                    "confidence": min(float(intent.get("confidence", 0.5)), 0.6),
                }
                fallback_intent["retrieval_steps"] = self._build_retrieval_steps(
                    query=query,
                    top_k=top_k,
                    execution_mode="direct_llm",
                    presentation_mode="direct_answer",
                    use_rag=False,
                    documents=[],
                    has_uploaded_image=False,
                    classifier_reason=str(fallback_intent.get("reason", "")),
                )
                return answer, [], fallback_intent
            answer = await self._answer_with_uploaded_image(
                query=query,
                image=image,
                chat_history=chat_history,
            )
            intent["retrieval_steps"] = self._build_retrieval_steps(
                query=query,
                top_k=top_k,
                execution_mode=execution_mode,
                presentation_mode=intent["presentation_mode"],
                use_rag=False,
                documents=[],
                has_uploaded_image=True,
                classifier_reason=str(intent.get("reason", "")),
            )
            return answer, [], intent

        if execution_mode == "save_uploaded_image":
            if image is None:
                answer = await self._answer_directly(query=query, chat_history=chat_history)
                fallback_intent = {
                    **intent,
                    "execution_mode": "direct_llm",
                    "presentation_mode": "direct_answer",
                    "use_rag": False,
                    "wants_images": False,
                    "reason": "save_uploaded_image_missing_fallback_to_direct",
                    "confidence": min(float(intent.get("confidence", 0.5)), 0.6),
                }
                fallback_intent["retrieval_steps"] = self._build_retrieval_steps(
                    query=query,
                    top_k=top_k,
                    execution_mode="direct_llm",
                    presentation_mode="direct_answer",
                    use_rag=False,
                    documents=[],
                    has_uploaded_image=False,
                    classifier_reason=str(fallback_intent.get("reason", "")),
                )
                return answer, [], fallback_intent
            answer, documents = await self._save_uploaded_image_to_kb(image)
            intent["retrieval_steps"] = self._build_retrieval_steps(
                query=query,
                top_k=top_k,
                execution_mode=execution_mode,
                presentation_mode=intent["presentation_mode"],
                use_rag=False,
                documents=documents,
                has_uploaded_image=True,
                classifier_reason=str(intent.get("reason", "")),
            )
            return answer, documents, intent

        if execution_mode == "image_similarity":
            documents = await self._retrieve_images_for_query(
                query=query,
                image=image,
                top_k=top_k,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
            )
            answer = self._build_image_only_answer(documents)
            intent["retrieval_steps"] = self._build_retrieval_steps(
                query=query,
                top_k=top_k,
                execution_mode=execution_mode,
                presentation_mode=intent["presentation_mode"],
                use_rag=False,
                documents=documents,
                has_uploaded_image=image is not None,
                classifier_reason=str(intent.get("reason", "")),
            )
            return answer, documents, intent

        if execution_mode == "image_grounded_answer":
            documents = await self._retrieve_images_for_query(
                query=query,
                image=image,
                top_k=top_k,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
            )
            answer = await self._answer_with_retrieved_images(
                query=query,
                documents=documents,
                chat_history=chat_history,
            )
            intent["retrieval_steps"] = self._build_retrieval_steps(
                query=query,
                top_k=top_k,
                execution_mode=execution_mode,
                presentation_mode=intent["presentation_mode"],
                use_rag=True,
                documents=documents,
                has_uploaded_image=image is not None,
                classifier_reason=str(intent.get("reason", "")),
            )
            return answer, documents, intent

        if execution_mode == "multimodal_rag":
            if image is not None:
                answer, documents = await self.rag_chain.ainvoke_with_image(
                    query=query,
                    image=image,
                    top_k=top_k,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                )
                intent["retrieval_steps"] = self._build_retrieval_steps(
                    query=query,
                    top_k=top_k,
                    execution_mode=execution_mode,
                    presentation_mode=intent["presentation_mode"],
                    use_rag=True,
                    documents=documents,
                    has_uploaded_image=True,
                    classifier_reason=str(intent.get("reason", "")),
                )
                return answer, documents, intent

            if force_agentic_rag:
                answer, documents, retrieval_steps = await run_agentic_multimodal_rag(
                    query=query,
                    top_k=top_k,
                    chat_history=chat_history,
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                    rag_chain=self.rag_chain,
                    retriever=self.retriever,
                    doc_vector_store=self.document_vector_store,
                    execution_mode=execution_mode,
                    presentation_mode=intent["presentation_mode"],
                    classifier_reason=str(intent.get("reason", "")),
                has_uploaded_image=False,
                retrieval_profile=retrieval_profile,
                    )
                intent["retrieval_steps"] = retrieval_steps
                return answer, documents, intent

        if execution_mode == "multimodal_rag":
            answer, documents = await self.rag_chain.ainvoke(
                {
                    "query": query,
                    "chat_history": chat_history or [],
                    "top_k": top_k,
                    "enable_score_filter": enable_score_filter,
                    "min_relevance_score": min_relevance_score,
                }
            )
            intent["retrieval_steps"] = self._build_retrieval_steps(
                query=query,
                top_k=top_k,
                execution_mode=execution_mode,
                presentation_mode=intent["presentation_mode"],
                use_rag=True,
                documents=documents,
                has_uploaded_image=False,
                classifier_reason=str(intent.get("reason", "")),
            )
            return answer, documents, intent

        answer = await self._answer_directly(query=query, chat_history=chat_history)
        fallback_intent = {
            **intent,
            "execution_mode": "direct_llm",
            "presentation_mode": "direct_answer",
            "use_rag": False,
            "wants_images": False,
            "reason": "unknown_execution_mode_fallback",
        }
        fallback_intent["retrieval_steps"] = self._build_retrieval_steps(
            query=query,
            top_k=top_k,
            execution_mode="direct_llm",
            presentation_mode="direct_answer",
            use_rag=False,
            documents=[],
            has_uploaded_image=image is not None,
            classifier_reason=str(fallback_intent.get("reason", "")),
        )
        return answer, [], fallback_intent

    async def _stream_chat_mode_response(
        self,
        *,
        query: str,
        top_k: int,
        image: Optional[UploadFile],
        chat_history: Optional[List[Tuple[str, str]]],
        enable_score_filter: bool,
        min_relevance_score: Optional[float],
        source_scope: Optional[Dict[str, List[str]]],
        chat_mode: ChatMode,
        emit_progress: bool = False,
    ):
        retrieval_profile = self._build_chat_mode_profile(chat_mode)
        if chat_mode == "fast":
            intent = _rule_based_intent(query, image is not None)
            if intent is None:
                if image is not None:
                    intent = self._build_forced_intent("uploaded_image_qa", True)
                    intent["reason"] = "fast_mode_uploaded_image_fallback"
                elif source_scope:
                    intent = self._build_forced_intent("multimodal_rag", False)
                    intent["reason"] = "fast_mode_scoped_rag_fallback"
                else:
                    intent = self._build_forced_intent("direct_llm", False)
                    intent["reason"] = "fast_mode_direct_fallback"
            force_agentic_rag = False
        else:
            intent = await classify_chat_intent(
                query=query,
                has_uploaded_image=image is not None,
                mode="expert",
            )
            force_agentic_rag = settings.CHAT_EXPERT_FORCE_AGENTIC_RAG

        collector = get_current_timing_collector()
        if collector is not None:
            collector.set_metadata(
                execution_mode=intent["execution_mode"],
                presentation_mode=intent["presentation_mode"],
            )

        async for event in self._stream_intent_chat(
            intent=intent,
            query=query,
            top_k=top_k,
            image=image,
            chat_history=chat_history,
            enable_score_filter=enable_score_filter,
            min_relevance_score=min_relevance_score,
            source_scope=source_scope,
            force_agentic_rag=force_agentic_rag,
            retrieval_profile=retrieval_profile,
            chat_mode=chat_mode,
            emit_progress=emit_progress,
        ):
            yield event

    async def _stream_intent_chat(
        self,
        *,
        intent: Dict[str, Any],
        query: str,
        top_k: int,
        image: Optional[UploadFile],
        chat_history: Optional[List[Tuple[str, str]]],
        enable_score_filter: bool,
        min_relevance_score: Optional[float],
        source_scope: Optional[Dict[str, List[str]]] = None,
        force_agentic_rag: bool = False,
        retrieval_profile: Optional[Dict[str, Any]] = None,
        chat_mode: ChatMode = "default",
        emit_progress: bool = False,
    ):
        execution_mode = intent["execution_mode"]
        query_rewrite_enabled = (
            settings.QUERY_REWRITE_ENABLED
            if retrieval_profile is None
            else bool(retrieval_profile.get("enable_query_rewrite", True))
        )
        rerank_enabled = (
            settings.RERANK_TOP_K > 0 and settings.RERANK_CANDIDATE_K > 0
            if retrieval_profile is None
            else bool(retrieval_profile.get("enable_rerank", True))
        )
        compression_enabled = (
            False
            if retrieval_profile is None
            else bool(retrieval_profile.get("enable_context_compression", False))
        )

        if emit_progress:
            yield self._build_progress_event(
                phase="routing",
                status="completed",
                title="routing",
                chat_mode=chat_mode,
                execution_mode=execution_mode,
                use_rag=bool(intent.get("use_rag", execution_mode in {"multimodal_rag", "image_grounded_answer"})),
                step_key="intent",
                detail="Route resolved",
                meta=self._progress_meta(
                    source_scope=source_scope,
                    classifier="rule" if chat_mode == "fast" else ("llm" if chat_mode == "expert" else "manual"),
                    agentic_enabled=force_agentic_rag and execution_mode == "multimodal_rag" and image is None and not source_scope,
                ),
            )

        if execution_mode == "direct_llm":
            if emit_progress:
                for phase in ("rewrite", "retrieve", "rerank", "compress"):
                    yield self._build_progress_event(
                        phase=phase,
                        status="skipped",
                        title=phase,
                        chat_mode=chat_mode,
                        execution_mode=execution_mode,
                        use_rag=False,
                        step_key="query" if phase == "rewrite" else "retrieve",
                        meta=self._progress_meta(
                            query_rewrite_enabled=False if phase == "rewrite" else None,
                            rerank_enabled=False if phase == "rerank" else None,
                            compression_enabled=False if phase == "compress" else None,
                        ),
                    )
                yield self._build_progress_event(
                    phase="generate",
                    status="started",
                    title="generate",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=False,
                    step_key="generate",
                    meta=self._progress_meta(generation_started=True),
                )
            intent["retrieval_steps"] = self._build_retrieval_steps(
                query=query,
                top_k=top_k,
                execution_mode="direct_llm",
                presentation_mode=intent["presentation_mode"],
                use_rag=False,
                documents=[],
                has_uploaded_image=image is not None,
                classifier_reason=str(intent.get("reason", "")),
            )
            async for chunk in self._astream_direct_answer(query=query, chat_history=chat_history):
                yield chunk, [], intent
            return

        if execution_mode == "uploaded_image_qa":
            if image is None:
                fallback_intent = {
                    **intent,
                    "execution_mode": "direct_llm",
                    "presentation_mode": "direct_answer",
                    "use_rag": False,
                    "wants_images": False,
                    "reason": "uploaded_image_missing_fallback_to_direct",
                    "confidence": min(float(intent.get("confidence", 0.5)), 0.6),
                }
                fallback_intent["retrieval_steps"] = self._build_retrieval_steps(
                    query=query,
                    top_k=top_k,
                    execution_mode="direct_llm",
                    presentation_mode="direct_answer",
                    use_rag=False,
                    documents=[],
                    has_uploaded_image=False,
                    classifier_reason=str(fallback_intent.get("reason", "")),
                )
                if emit_progress:
                    for phase in ("rewrite", "retrieve", "rerank", "compress"):
                        yield self._build_progress_event(
                            phase=phase,
                            status="skipped",
                            title=phase,
                            chat_mode=chat_mode,
                            execution_mode="direct_llm",
                            use_rag=False,
                            step_key="query" if phase == "rewrite" else "retrieve",
                            meta=self._progress_meta(
                                query_rewrite_enabled=False if phase == "rewrite" else None,
                                rerank_enabled=False if phase == "rerank" else None,
                                compression_enabled=False if phase == "compress" else None,
                            ),
                        )
                    yield self._build_progress_event(
                        phase="generate",
                        status="started",
                        title="generate",
                        chat_mode=chat_mode,
                        execution_mode="direct_llm",
                        use_rag=False,
                        step_key="generate",
                        meta=self._progress_meta(generation_started=True),
                    )
                async for chunk in self._astream_direct_answer(query=query, chat_history=chat_history):
                    yield chunk, [], fallback_intent
                return
            if emit_progress:
                for phase in ("rewrite", "retrieve", "rerank", "compress"):
                    yield self._build_progress_event(
                        phase=phase,
                        status="skipped",
                        title=phase,
                        chat_mode=chat_mode,
                        execution_mode=execution_mode,
                        use_rag=False,
                        step_key="query" if phase == "rewrite" else "retrieve",
                        meta=self._progress_meta(
                            query_rewrite_enabled=False if phase == "rewrite" else None,
                            rerank_enabled=False if phase == "rerank" else None,
                            compression_enabled=False if phase == "compress" else None,
                        ),
                    )
                yield self._build_progress_event(
                    phase="generate",
                    status="started",
                    title="generate",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=False,
                    step_key="generate",
                    meta=self._progress_meta(generation_started=True),
                )
            intent["retrieval_steps"] = self._build_retrieval_steps(
                query=query,
                top_k=top_k,
                execution_mode="uploaded_image_qa",
                presentation_mode=intent["presentation_mode"],
                use_rag=False,
                documents=[],
                has_uploaded_image=True,
                classifier_reason=str(intent.get("reason", "")),
            )
            async for chunk in self._astream_uploaded_image_answer(
                query=query,
                image=image,
                chat_history=chat_history,
            ):
                yield chunk, [], intent
            return

        if execution_mode == "multimodal_rag" and force_agentic_rag and image is None and not source_scope:
            if emit_progress:
                yield self._build_progress_event(
                    phase="rewrite",
                    status="started" if query_rewrite_enabled else "skipped",
                    title="rewrite",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="query",
                    meta=self._progress_meta(query_rewrite_enabled=query_rewrite_enabled),
                )
                yield self._build_progress_event(
                    phase="retrieve",
                    status="started",
                    title="retrieve",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="retrieve",
                )
                yield self._build_progress_event(
                    phase="rerank",
                    status="started" if rerank_enabled else "skipped",
                    title="rerank",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="retrieve",
                    meta=self._progress_meta(rerank_enabled=rerank_enabled),
                )
                yield self._build_progress_event(
                    phase="compress",
                    status="started" if compression_enabled else "skipped",
                    title="compress",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="retrieve",
                    meta=self._progress_meta(compression_enabled=compression_enabled),
                )
                yield self._build_progress_event(
                    phase="agentic",
                    status="started",
                    title="agentic",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="retrieve",
                    meta=self._progress_meta(agentic_enabled=True),
                )
            final_state, docs, text_chunks, retrieval_steps = await prepare_agentic_multimodal_rag_context(
                query=query,
                top_k=top_k,
                chat_history=chat_history,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
                rag_chain=self.rag_chain,
                retriever=self.retriever,
                doc_vector_store=self.document_vector_store,
                execution_mode=execution_mode,
                presentation_mode=intent["presentation_mode"],
                classifier_reason=str(intent.get("reason", "")),
                has_uploaded_image=False,
                retrieval_profile=retrieval_profile,
            )
            intent["retrieval_steps"] = retrieval_steps
            if emit_progress:
                if query_rewrite_enabled:
                    yield self._build_progress_event(
                        phase="rewrite",
                        status="completed",
                        title="rewrite",
                        chat_mode=chat_mode,
                        execution_mode=execution_mode,
                        use_rag=True,
                        step_key="query",
                        meta=self._progress_meta(query_rewrite_enabled=True),
                    )
                yield self._build_progress_event(
                    phase="retrieve",
                    status="completed",
                    title="retrieve",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="retrieve",
                    meta=self._progress_meta(retrieved_candidates=len(docs) + len(text_chunks)),
                )
                if rerank_enabled:
                    yield self._build_progress_event(
                        phase="rerank",
                        status="completed",
                        title="rerank",
                        chat_mode=chat_mode,
                        execution_mode=execution_mode,
                        use_rag=True,
                        step_key="retrieve",
                        meta=self._progress_meta(rerank_enabled=True),
                    )
                if compression_enabled:
                    yield self._build_progress_event(
                        phase="compress",
                        status="completed",
                        title="compress",
                        chat_mode=chat_mode,
                        execution_mode=execution_mode,
                        use_rag=True,
                        step_key="retrieve",
                        meta=self._progress_meta(compression_enabled=True),
                    )
                yield self._build_progress_event(
                    phase="agentic",
                    status="completed",
                    title="agentic",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="retrieve",
                    meta=self._progress_meta(agentic_enabled=True),
                )
                yield self._build_progress_event(
                    phase="generate",
                    status="started",
                    title="generate",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="generate",
                    meta=self._progress_meta(generation_started=True),
                )
            async for chunk in self.rag_chain.astream_from_context(
                query=query,
                documents=docs,
                text_chunks=text_chunks,
                chat_history=chat_history or [],
            ):
                yield chunk, docs, intent
            return

        if execution_mode in {"multimodal_rag", "image_grounded_answer"}:
            if emit_progress:
                yield self._build_progress_event(
                    phase="rewrite",
                    status="started" if query_rewrite_enabled else "skipped",
                    title="rewrite",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="query",
                    meta=self._progress_meta(query_rewrite_enabled=query_rewrite_enabled),
                )
                yield self._build_progress_event(
                    phase="retrieve",
                    status="started",
                    title="retrieve",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="retrieve",
                )
                yield self._build_progress_event(
                    phase="rerank",
                    status="started" if rerank_enabled else "skipped",
                    title="rerank",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="retrieve",
                    meta=self._progress_meta(rerank_enabled=rerank_enabled),
                )
            scoped_context = await self._prepare_scoped_chat_context(
                query=query,
                top_k=top_k,
                image=image,
                chat_history=chat_history,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
                execution_hint=execution_mode,
                source_scope=source_scope,
                retrieval_profile=retrieval_profile,
            )
            if emit_progress:
                if query_rewrite_enabled:
                    yield self._build_progress_event(
                        phase="rewrite",
                        status="completed",
                        title="rewrite",
                        chat_mode=chat_mode,
                        execution_mode=execution_mode,
                        use_rag=True,
                        step_key="query",
                        meta=self._progress_meta(query_rewrite_enabled=True),
                    )
                yield self._build_progress_event(
                    phase="retrieve",
                    status="completed",
                    title="retrieve",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="retrieve",
                    meta=self._progress_meta(
                        retrieved_candidates=len(scoped_context["combined_documents"]),
                        source_scope=source_scope,
                    ),
                )
                if rerank_enabled:
                    yield self._build_progress_event(
                        phase="rerank",
                        status="completed",
                        title="rerank",
                        chat_mode=chat_mode,
                        execution_mode=execution_mode,
                        use_rag=True,
                        step_key="retrieve",
                        meta=self._progress_meta(rerank_enabled=True),
                    )
                yield self._build_progress_event(
                    phase="compress",
                    status="completed" if compression_enabled and scoped_context["generation_documents"] else "skipped",
                    title="compress",
                    chat_mode=chat_mode,
                    execution_mode=execution_mode,
                    use_rag=True,
                    step_key="retrieve",
                    meta=self._progress_meta(compression_enabled=compression_enabled and bool(scoped_context["generation_documents"])),
                )
            if scoped_context["streaming_ready"] and (
                retrieval_profile is None
                or retrieval_profile.get("force_true_streaming", False)
            ):
                intent["retrieval_steps"] = self._build_retrieval_steps(
                    query=scoped_context["scoped_query"],
                    top_k=top_k,
                    execution_mode=execution_mode,
                    presentation_mode=intent["presentation_mode"],
                    use_rag=True,
                    documents=scoped_context["combined_documents"],
                    has_uploaded_image=image is not None,
                    classifier_reason=str(intent.get("reason", "")),
                )
                if emit_progress:
                    yield self._build_progress_event(
                        phase="generate",
                        status="started",
                        title="generate",
                        chat_mode=chat_mode,
                        execution_mode=execution_mode,
                        use_rag=True,
                        step_key="generate",
                        meta=self._progress_meta(generation_started=True),
                    )
                async for chunk in self.rag_chain.astream_from_context(
                    query=scoped_context["generation_query"],
                    documents=scoped_context["generation_documents"],
                    text_chunks=scoped_context["generation_text_chunks"],
                    chat_history=scoped_context["generation_history"],
                ):
                    yield chunk, scoped_context["combined_documents"], intent
                return

        answer, docs, final_intent = await self._run_intent_chat(
            intent=intent,
            query=query,
            top_k=top_k,
            image=image,
            chat_history=chat_history,
            enable_score_filter=enable_score_filter,
            min_relevance_score=min_relevance_score,
            source_scope=source_scope,
            force_agentic_rag=force_agentic_rag,
            retrieval_profile=retrieval_profile,
        )
        if emit_progress:
            yield self._build_progress_event(
                phase="generate",
                status="started",
                title="generate",
                chat_mode=chat_mode,
                execution_mode=final_intent.get("execution_mode", execution_mode),
                use_rag=bool(final_intent.get("use_rag", execution_mode in {"multimodal_rag", "image_grounded_answer"})),
                step_key="generate",
                meta=self._progress_meta(generation_started=True),
            )
        for ch in self._iter_answer_chunks(answer):
            yield ch, docs, final_intent

    def _iter_answer_chunks(self, answer: str) -> Iterator[str]:
        """将最终答案切成可回放的小块，供流式接口复用。"""
        for ch in answer:
            yield ch

    def _extract_stream_chunk_text(self, chunk: Any) -> str:
        """从模型/Chain 流式 chunk 中提取纯文本。"""
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

    def _build_default_intent(self, has_uploaded_image: bool) -> Dict[str, Any]:
        """未启用 Agentic 时提供兼容的默认意图元数据。"""
        return {
            "presentation_mode": "rag_answer",
            "execution_mode": "multimodal_rag",
            "use_rag": True,
            "has_uploaded_image": has_uploaded_image,
            "wants_images": has_uploaded_image,
            "confidence": 1.0,
            "reason": "legacy_rag_path",
        }

    def _build_forced_intent(self, execution_hint: str, has_uploaded_image: bool) -> Dict[str, Any]:
        mapping = {
            "direct_llm": ("direct_answer", False, False),
            "multimodal_rag": ("rag_answer", True, has_uploaded_image),
            "image_similarity": ("image_only", False, True),
            "image_grounded_answer": ("image_plus_answer", True, True),
            "uploaded_image_qa": ("direct_answer", False, False),
            "save_uploaded_image": ("direct_answer", False, False),
        }
        presentation_mode, use_rag, wants_images = mapping.get(
            execution_hint,
            ("rag_answer", True, has_uploaded_image),
        )
        return {
            "presentation_mode": presentation_mode,
            "execution_mode": execution_hint,
            "use_rag": use_rag,
            "has_uploaded_image": has_uploaded_image,
            "wants_images": wants_images,
            "confidence": 1.0,
            "reason": "manual_execution_hint",
        }

    async def _prepare_image_grounded_answer_context(
        self,
        *,
        query: str,
        documents: List[Dict[str, Any]],
        chat_history: Optional[List[Tuple[str, str]]],
        source_scope: Optional[Dict[str, List[str]]] = None,
        retrieval_profile: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Tuple[str, str]]]:
        """准备 image_grounded_answer 的最终生成上下文。"""
        if not documents:
            return [], [], []

        max_images = max(1, settings.IMAGE_GROUNDED_MAX_IMAGES)
        max_history_turns = max(0, settings.IMAGE_GROUNDED_MAX_HISTORY_TURNS)
        grounded_documents = documents[:max_images]
        grounded_history = (chat_history or [])[-max_history_turns:] if max_history_turns else []

        text_chunks: List[Dict[str, Any]] = []
        if settings.IMAGE_GROUNDED_TEXT_AUGMENT_ENABLED and settings.IMAGE_GROUNDED_TEXT_TOP_K > 0:
            if retrieval_profile:
                text_chunks = await self.document_vector_store.async_search_with_pipeline(
                    query,
                    top_k=settings.IMAGE_GROUNDED_TEXT_TOP_K,
                    candidate_k=retrieval_profile.get("candidate_k"),
                    enable_query_rewrite=bool(retrieval_profile.get("enable_query_rewrite", True)),
                    query_rewrite_count=retrieval_profile.get("query_rewrite_count"),
                    enable_rerank=bool(retrieval_profile.get("enable_rerank", True)),
                )
            else:
                text_chunks = self.document_vector_store.search_with_pipeline(
                    query,
                    top_k=settings.IMAGE_GROUNDED_TEXT_TOP_K,
                )
            text_chunks = self._filter_text_chunks_by_source_scope(text_chunks, source_scope or {})

        return grounded_documents, text_chunks, grounded_history

    async def _prepare_scoped_chat_context(
        self,
        *,
        query: str,
        top_k: int,
        image: Optional[UploadFile],
        chat_history: Optional[List[Tuple[str, str]]],
        enable_score_filter: bool,
        min_relevance_score: Optional[float],
        execution_hint: str,
        source_scope: Optional[Dict[str, List[str]]],
        retrieval_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """准备 scoped chat 的上下文，不执行最终答案生成。"""
        intent = self._build_forced_intent(execution_hint, image is not None)
        scope = source_scope or {}
        scoped_query = query

        if image is not None and execution_hint in {"multimodal_rag", "image_similarity", "image_grounded_answer"}:
            scoped_query = await self.image_description_chain.ainvoke_from_uploadfile(image)
            await image.seek(0)

        documents: List[Dict[str, Any]] = []
        text_chunks: List[Dict[str, Any]] = []

        if execution_hint in {"multimodal_rag", "image_similarity", "image_grounded_answer"}:
            documents = await self._retrieve_images_for_query(
                query=scoped_query,
                image=image if execution_hint == "image_similarity" else None,
                top_k=max(top_k * 4, top_k),
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
                retrieval_profile=retrieval_profile,
            )
            documents = self._filter_documents_by_source_scope(documents, scope)

        generation_documents: List[Dict[str, Any]] = []
        generation_text_chunks: List[Dict[str, Any]] = []
        generation_history: List[Tuple[str, str]] = chat_history or []
        combined_documents: List[Dict[str, Any]] = []
        streaming_ready = False

        if execution_hint == "multimodal_rag":
            if retrieval_profile:
                text_chunks = await self.document_vector_store.async_search_with_pipeline(
                    scoped_query,
                    top_k=self.rag_chain.text_top_k,
                    candidate_k=retrieval_profile.get("candidate_k") or max(self.rag_chain.text_top_k * 4, self.rag_chain.text_top_k),
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                    enable_query_rewrite=bool(retrieval_profile.get("enable_query_rewrite", True)),
                    query_rewrite_count=retrieval_profile.get("query_rewrite_count"),
                    enable_rerank=bool(retrieval_profile.get("enable_rerank", True)),
                )
            else:
                text_chunks = self.document_vector_store.search_with_pipeline(
                    scoped_query,
                    top_k=self.rag_chain.text_top_k,
                    candidate_k=max(self.rag_chain.text_top_k * 4, self.rag_chain.text_top_k),
                    enable_score_filter=enable_score_filter,
                    min_relevance_score=min_relevance_score,
                )
            text_chunks = self._filter_text_chunks_by_source_scope(text_chunks, scope)
            generation_documents = documents
            generation_text_chunks = text_chunks
            combined_documents = documents + text_chunks
            streaming_ready = True
        elif execution_hint == "image_grounded_answer":
            generation_documents, generation_text_chunks, generation_history = await self._prepare_image_grounded_answer_context(
                query=scoped_query,
                documents=documents,
                chat_history=chat_history,
                source_scope=scope,
                retrieval_profile=retrieval_profile,
            )
            combined_documents = generation_documents + generation_text_chunks
            streaming_ready = bool(generation_documents)

        if retrieval_profile and generation_documents:
            from app.langchain_integration.context_compression import compress_context

            generation_documents = await compress_context(
                scoped_query,
                generation_documents,
                force_enabled=bool(retrieval_profile.get("enable_context_compression", False)),
            )
            combined_documents = generation_documents + generation_text_chunks

        return {
            "intent": intent,
            "scoped_query": scoped_query,
            "documents": documents,
            "text_chunks": text_chunks,
            "generation_query": scoped_query,
            "generation_documents": generation_documents,
            "generation_text_chunks": generation_text_chunks,
            "generation_history": generation_history,
            "combined_documents": combined_documents,
            "streaming_ready": streaming_ready,
        }

    async def _run_scoped_chat(
        self,
        *,
        query: str,
        top_k: int,
        image: Optional[UploadFile],
        chat_history: Optional[List[Tuple[str, str]]],
        enable_score_filter: bool,
        min_relevance_score: Optional[float],
        execution_hint: str,
        source_scope: Optional[Dict[str, List[str]]],
        retrieval_profile: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        scoped_context = await self._prepare_scoped_chat_context(
            query=query,
            top_k=top_k,
            image=image,
            chat_history=chat_history,
            enable_score_filter=enable_score_filter,
            min_relevance_score=min_relevance_score,
            execution_hint=execution_hint,
            source_scope=source_scope,
            retrieval_profile=retrieval_profile,
        )
        intent = scoped_context["intent"]
        scoped_query = scoped_context["scoped_query"]
        documents = scoped_context["documents"]
        text_chunks = scoped_context["text_chunks"]

        if execution_hint == "direct_llm":
            answer = await self._answer_directly(query=query, chat_history=chat_history)
            documents = []
            text_chunks = []
            intent["use_rag"] = False
        elif execution_hint == "uploaded_image_qa":
            if image is None:
                answer = await self._answer_directly(query=query, chat_history=chat_history)
            else:
                answer = await self._answer_with_uploaded_image(query=query, image=image, chat_history=chat_history)
            documents = []
            text_chunks = []
            intent["use_rag"] = False
        elif execution_hint == "save_uploaded_image":
            if image is None:
                answer = await self._answer_directly(query=query, chat_history=chat_history)
                documents = []
            else:
                answer, documents = await self._save_uploaded_image_to_kb(image)
            text_chunks = []
            intent["use_rag"] = False
        elif execution_hint == "image_similarity":
            answer = self._build_image_only_answer(documents)
            intent["use_rag"] = False
        else:
            if execution_hint == "image_grounded_answer" and not scoped_context["generation_documents"]:
                answer = "未找到相关图片，暂时无法根据知识库给出可靠回答。"
                documents = []
                text_chunks = []
                intent["use_rag"] = True
            else:
                answer = await self.rag_chain.agenerate_from_context(
                    query=scoped_context["generation_query"],
                    documents=scoped_context["generation_documents"],
                    text_chunks=scoped_context["generation_text_chunks"],
                    chat_history=scoped_context["generation_history"],
                )
                documents = scoped_context["combined_documents"]
                text_chunks = []
                intent["use_rag"] = True

        combined_documents = documents + text_chunks
        intent["retrieval_steps"] = self._build_retrieval_steps(
            query=scoped_query,
            top_k=top_k,
            execution_mode=intent["execution_mode"],
            presentation_mode=intent["presentation_mode"],
            use_rag=bool(intent["use_rag"]),
            documents=combined_documents,
            has_uploaded_image=image is not None,
            classifier_reason=str(intent.get("reason", "")),
        )
        return answer, combined_documents, intent

    def _filter_documents_by_source_scope(
        self,
        documents: List[Dict[str, Any]],
        source_scope: Dict[str, List[str]],
    ) -> List[Dict[str, Any]]:
        doc_ids = set(source_scope.get("doc_ids") or [])
        image_ids = set(source_scope.get("image_ids") or [])
        if not doc_ids and not image_ids:
            return documents

        filtered: List[Dict[str, Any]] = []
        for item in documents:
            metadata = item.get("metadata") or {}
            item_id = str(item.get("id") or metadata.get("id") or "").strip()
            doc_id = str(item.get("doc_id") or metadata.get("doc_id") or "").strip()
            if item_id and item_id in image_ids:
                filtered.append(item)
                continue
            if doc_id and doc_id in doc_ids:
                filtered.append(item)
        return filtered

    def _filter_text_chunks_by_source_scope(
        self,
        text_chunks: List[Dict[str, Any]],
        source_scope: Dict[str, List[str]],
    ) -> List[Dict[str, Any]]:
        doc_ids = set(source_scope.get("doc_ids") or [])
        if not doc_ids:
            return text_chunks
        return [item for item in text_chunks if str(item.get("doc_id") or "").strip() in doc_ids]

    def _build_retrieval_steps(
        self,
        *,
        query: str,
        top_k: int,
        execution_mode: str,
        presentation_mode: str,
        use_rag: bool,
        documents: List[Dict[str, Any]],
        has_uploaded_image: bool,
        classifier_reason: str,
    ) -> List[Dict[str, Any]]:
        score_values = [
            float(score)
            for score in (
                item.get("rerank_score", item.get("rrf_score", item.get("score")))
                for item in documents
                if isinstance(item, dict)
            )
            if score is not None
        ]
        source_types = sorted(
            {
                str((item.get("metadata") or {}).get("asset_type") or ("document_chunk" if item.get("doc_id") is not None else "image"))
                for item in documents
                if isinstance(item, dict)
            }
        )
        top_ids = [
            str(item.get("id") or (item.get("metadata") or {}).get("id") or item.get("doc_id"))
            for item in documents[:3]
            if isinstance(item, dict)
        ]
        steps: List[Dict[str, Any]] = [
            {
                "key": "intent",
                "label": "意图",
                "summary": f"{execution_mode} / {presentation_mode}",
                "details": {
                    "execution_mode": execution_mode,
                    "presentation_mode": presentation_mode,
                    "use_rag": use_rag,
                    "has_uploaded_image": has_uploaded_image,
                    "reason": classifier_reason,
                },
            },
            {
                "key": "query",
                "label": "查询",
                "summary": query[:120],
                "details": {
                    "query": query,
                    "top_k": top_k,
                },
            },
        ]
        if use_rag or documents:
            steps.append(
                {
                    "key": "retrieval",
                    "label": "检索",
                    "summary": f"召回 {len(documents)} 条结果",
                    "details": {
                        "count": len(documents),
                        "top_source_ids": [item for item in top_ids if item and item != "None"],
                        "source_types": source_types,
                    },
                }
            )
        if score_values:
            avg_score = sum(score_values) / len(score_values)
            steps.append(
                {
                    "key": "grading",
                    "label": "评分",
                    "summary": f"平均分 {avg_score:.3f}，最高分 {max(score_values):.3f}",
                    "details": {
                        "avg_rerank_score": round(avg_score, 6),
                        "max_rerank_score": round(max(score_values), 6),
                        "min_rerank_score": round(min(score_values), 6),
                        "scored_count": len(score_values),
                    },
                }
            )
        return steps

    async def _answer_directly(
        self,
        query: str,
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """不经过知识库检索，直接调用回答模型。"""
        history_text = "\n".join(f"用户：{q}\n助手：{a}" for q, a in (chat_history or [])[-5:])
        prompt = f"""你是一个专业问答助手，请直接回答用户问题。

对话历史：
{history_text}

用户问题：{query}
"""
        model = get_primary_text_chat_model()
        result = await model._agenerate([HumanMessage(content=prompt)])
        return result.generations[0].message.content

    async def _astream_direct_answer(
        self,
        query: str,
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ):
        """直接调用文本模型进行真流式回答。"""
        history_text = "\n".join(f"用户：{q}\n助手：{a}" for q, a in (chat_history or [])[-5:])
        prompt = f"""你是一个专业问答助手，请直接回答用户问题。

对话历史：
{history_text}

用户问题：{query}
"""
        model = get_primary_text_chat_model()
        async for chunk in model._astream([HumanMessage(content=prompt)]):
            text = self._extract_stream_chunk_text(chunk)
            if text:
                yield text

    async def _answer_with_uploaded_image(
        self,
        query: str,
        image: UploadFile,
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """只基于用户上传图片本身进行回答。"""
        contents = await image.read()
        await image.seek(0)
        image_b64 = base64.b64encode(contents).decode("utf-8")
        mime_type = image.content_type or guess_image_mime_type(image.filename)
        history_text = "\n".join(f"用户：{q}\n助手：{a}" for q, a in (chat_history or [])[-5:])
        prompt = (
            "你是一个图片问答助手。只基于用户当前上传的图片内容回答问题，"
            "不要引用知识库或臆测图片外信息。如果图片中没有足够信息，请明确说明。"
            f"\n\n对话历史：\n{history_text}\n\n用户问题：{query}"
        )
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": build_image_data_url(image_b64, mime_type)}},
            ]
        )
        model = get_multimodal_chat_model()
        result = await model._agenerate([message])
        return result.generations[0].message.content

    async def _astream_uploaded_image_answer(
        self,
        query: str,
        image: UploadFile,
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ):
        """只基于用户上传图片本身进行真流式回答。"""
        contents = await image.read()
        await image.seek(0)
        image_b64 = base64.b64encode(contents).decode("utf-8")
        mime_type = image.content_type or guess_image_mime_type(image.filename)
        history_text = "\n".join(f"用户：{q}\n助手：{a}" for q, a in (chat_history or [])[-5:])
        prompt = (
            "你是一个图片问答助手。只基于用户当前上传的图片内容回答问题，"
            "不要引用知识库或臆测图片外信息。如果图片中没有足够信息，请明确说明。"
            f"\n\n对话历史：\n{history_text}\n\n用户问题：{query}"
        )
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": build_image_data_url(image_b64, mime_type)}},
            ]
        )
        model = get_multimodal_chat_model()
        async for chunk in model._astream([message]):
            text = self._extract_stream_chunk_text(chunk)
            if text:
                yield text

    async def _retrieve_images_for_query(
        self,
        query: str,
        image: Optional[UploadFile],
        top_k: int,
        enable_score_filter: bool = False,
        min_relevance_score: Optional[float] = None,
        retrieval_profile: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """根据文本或上传图片检索知识库图片。"""
        use_fast_path = True if retrieval_profile is None else bool(retrieval_profile.get("image_fast_path", False))
        candidate_k = None if retrieval_profile is None else retrieval_profile.get("candidate_k")
        enable_query_rewrite = None if retrieval_profile is None else bool(retrieval_profile.get("enable_query_rewrite", True))
        query_rewrite_count = None if retrieval_profile is None else retrieval_profile.get("query_rewrite_count")
        enable_rerank = True if retrieval_profile is None else bool(retrieval_profile.get("enable_rerank", True))
        if image is not None:
            documents, _description = await self.image_to_image_search(
                image,
                top_k=top_k,
                fast=use_fast_path,
                enable_score_filter=enable_score_filter,
                min_relevance_score=min_relevance_score,
                candidate_k=candidate_k,
                enable_query_rewrite=enable_query_rewrite,
                query_rewrite_count=query_rewrite_count,
                enable_rerank=enable_rerank,
            )
            return documents
        return await self.text_to_image_search(
            query,
            top_k=top_k,
            fast=use_fast_path,
            enable_score_filter=enable_score_filter,
            min_relevance_score=min_relevance_score,
            candidate_k=candidate_k,
            enable_query_rewrite=enable_query_rewrite,
            query_rewrite_count=query_rewrite_count,
            enable_rerank=enable_rerank,
        )

    def _build_image_only_answer(self, documents: List[Dict[str, Any]]) -> str:
        """为纯找图请求生成简短说明。"""
        if not documents:
            return "未找到相关图片。"
        return f"为你找到 {len(documents)} 张相关图片。"

    async def _save_uploaded_image_to_kb(
        self,
        image: UploadFile,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """将聊天页上传图片直接存入图片知识库。"""
        from app.data.database import SessionLocal

        with SessionLocal() as db:
            record, description, deduplicated, _duplicate_of = await self.process_image_upload(
                db=db,
                file=image,
                split="custom",
                source_dataset="chat_upload",
            )

        title = record.title or Path(record.file_path).stem
        answer = f"图片“{title}”已存在，已复用现有知识库记录。" if deduplicated else f"已将图片“{title}”存入图片知识库。"
        return answer, [
            {
                "id": record.id,
                "document": description,
                "metadata": {
                    "id": record.id,
                    "file_path": record.file_path,
                    "source_dataset": record.source_dataset,
                    "title": title,
                    "enabled": bool(getattr(record, "enabled", True)),
                },
                "score": 1.0,
            }
        ]

    async def _answer_with_retrieved_images(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """基于检索到的图片和相关文本生成回答。"""
        if not documents:
            return "未找到相关图片，暂时无法根据知识库给出可靠回答。"

        max_images = max(1, settings.IMAGE_GROUNDED_MAX_IMAGES)
        max_history_turns = max(0, settings.IMAGE_GROUNDED_MAX_HISTORY_TURNS)
        grounded_documents = documents[:max_images]
        grounded_history = (chat_history or [])[-max_history_turns:] if max_history_turns else []

        text_chunks: List[Dict[str, Any]] = []
        if settings.IMAGE_GROUNDED_TEXT_AUGMENT_ENABLED and settings.IMAGE_GROUNDED_TEXT_TOP_K > 0:
            text_chunks = self.document_vector_store.search_with_pipeline(
                query,
                top_k=settings.IMAGE_GROUNDED_TEXT_TOP_K,
            )

        return await self.rag_chain.agenerate_from_context(
            query=query,
            documents=grounded_documents,
            text_chunks=text_chunks,
            chat_history=grounded_history,
        )

    def _rebuild_bm25_index(self) -> None:
        """全量重建 BM25 索引（仅用于启动和手动触发）"""
        try:
            from app.retrieval.hybrid import rebuild_bm25_index
            rebuild_bm25_index()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Adapter] BM25 索引重建失败: {e}")

    def _bm25_add_document(self, doc_id: str, text: str) -> None:
        """增量添加单篇文档到 BM25 索引"""
        try:
            from app.retrieval.hybrid import get_bm25_index
            index = get_bm25_index()
            index.add_document(doc_id, text)
            index.save()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Adapter] BM25 增量更新失败: {e}")

    def _bm25_add_chunks(self, doc_id: str, text_chunks: List[str], image_count: int) -> None:
        """增量添加 PDF 的文本片段到 BM25 索引"""
        try:
            from app.retrieval.hybrid import get_bm25_index
            index = get_bm25_index()
            for i, chunk in enumerate(text_chunks):
                chunk_id = f"{doc_id}_chunk_{i}"
                index.add_document(chunk_id, chunk)
            if text_chunks or image_count > 0:
                index.save()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Adapter] BM25 增量更新失败: {e}")

    def _is_transient_external_error(self, exc: Exception) -> bool:
        message = str(exc).strip().lower()
        return any(marker in message for marker in _TRANSIENT_EXTERNAL_ERROR_MARKERS)

    def _upsert_document_chunks_with_retry(
        self,
        doc_id: str,
        chunks: List[str],
        metadatas: List[Dict[str, Any]],
        max_attempts: int = 3,
    ) -> None:
        for attempt in range(1, max_attempts + 1):
            try:
                self.document_vector_store.upsert_chunks(
                    doc_id=doc_id,
                    chunks=chunks,
                    metadatas=metadatas,
                )
                return
            except Exception as exc:
                is_transient = self._is_transient_external_error(exc)
                if attempt >= max_attempts or not is_transient:
                    raise
                logger.warning(
                    "[Adapter] 文档向量写入失败，进行重试: doc=%s attempt=%s/%s error=%s",
                    doc_id,
                    attempt,
                    max_attempts,
                    exc,
                )
                time.sleep(min(0.5 * attempt, 1.5))

    def get_vector_store_stats(self) -> Dict[str, Any]:
        """
        获取向量存储统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            collection = self.vector_store.vectorstore._collection
            count = collection.count()
            return {
                "total_documents": count,
                "collection_name": self.vector_store.collection_name,
                "persist_directory": self.vector_store.persist_directory,
            }
        except Exception as e:
            return {
                "error": str(e),
                "collection_name": self.vector_store.collection_name,
            }

    async def create_document_upload_record(
        self,
        db: Session,
        file: UploadFile,
        logical_asset_id: Optional[str] = None,
    ) -> Tuple[DocumentRecord, bool, Optional[str]]:
        """创建文档记录并保存原始文件，不阻塞等待解析完成。"""
        ensure_knowledge_management_columns(db)
        doc_id = str(uuid.uuid4())
        contents = await file.read()
        file_name = file.filename or "document.pdf"
        content_hash = self._compute_content_hash(contents)

        existing = (
            db.query(DocumentRecord)
            .filter(DocumentRecord.content_hash == content_hash, DocumentRecord.is_latest.is_(True))
            .first()
        )
        if existing is not None:
            return existing, True, existing.id

        doc_path = get_doc_path(doc_id)
        with open(str(doc_path), "wb") as f:
            f.write(contents)

        resolved_logical_asset_id = logical_asset_id or doc_id
        version_number = self._next_document_version(db, resolved_logical_asset_id) if logical_asset_id else 1
        if logical_asset_id:
            db.query(DocumentRecord).filter(
                DocumentRecord.logical_asset_id == resolved_logical_asset_id,
                DocumentRecord.is_latest.is_(True),
            ).update({"is_latest": False})

        record = DocumentRecord(
            id=doc_id,
            file_name=file_name,
            title=os.path.splitext(file_name)[0],
            file_path=str(doc_path),
            document_type="pdf",
            status="Processing",
            parse_backend=settings.DOC_PARSE_BACKEND,
            parse_stage="queued",
            progress_percent=0,
            progress_message="文档已上传，等待解析",
            content_hash=content_hash,
            logical_asset_id=resolved_logical_asset_id,
            version_number=version_number,
            is_latest=True,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record, False, None

    def _set_document_progress(
        self,
        db: Session,
        record: DocumentRecord,
        *,
        stage: str,
        percent: int,
        message: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        record.parse_stage = stage
        record.progress_percent = max(0, min(100, int(percent)))
        if message is not None:
            record.progress_message = message
        if status is not None:
            record.status = status
        db.add(record)
        db.commit()
        db.refresh(record)

    def _mark_document_failed(
        self,
        db: Session,
        *,
        doc_id: str,
        error_message: str,
    ) -> None:
        db.rollback()
        record = db.query(DocumentRecord).filter(DocumentRecord.id == doc_id).first()
        if record is None:
            logger.warning("[Adapter] 文档后台解析目标不存在: %s", doc_id)
            return
        record.parse_stage = "failed"
        record.progress_percent = 100
        record.progress_message = error_message
        record.status = "Failed"
        record.extra_metadata = error_message
        db.add(record)
        db.commit()

    async def process_document_record_task(self, doc_id: str) -> None:
        """后台任务入口：按配置解析指定文档。"""
        with SessionLocal() as db:
            ensure_knowledge_management_columns(db)
            record = db.query(DocumentRecord).filter(DocumentRecord.id == doc_id).first()
            if record is None:
                logger.warning("[Adapter] 文档后台解析目标不存在: %s", doc_id)
                return
            try:
                await self._process_document_record(db, record)
            except Exception as exc:
                logger.exception("[Adapter] 文档后台解析失败: doc=%s error=%s", doc_id, exc)
                self._mark_document_failed(db, doc_id=doc_id, error_message=str(exc))
                raise

    async def reprocess_document_record_task(self, doc_id: str) -> None:
        """后台重处理任务入口。"""
        with SessionLocal() as db:
            ensure_knowledge_management_columns(db)
            record = db.query(DocumentRecord).filter(DocumentRecord.id == doc_id).first()
            if record is None:
                logger.warning("[Adapter] 文档后台重处理目标不存在: %s", doc_id)
                return
            try:
                self.delete_document_record(db, record, preserve_record=True)
                record.chunk_count = 0
                record.image_count = 0
                db.commit()
                await self._process_document_record(db, record)
            except Exception as exc:
                logger.exception("[Adapter] 文档后台重处理失败: doc=%s error=%s", doc_id, exc)
                self._mark_document_failed(db, doc_id=doc_id, error_message=str(exc))
                raise

    async def _process_document_record(self, db: Session, record: DocumentRecord) -> None:
        backend = (record.parse_backend or settings.DOC_PARSE_BACKEND or "local").strip().lower()
        if backend not in {"local", "mineru"}:
            raise ValueError(f"Unsupported document parse backend: {backend}")

        self._set_document_progress(
            db,
            record,
            stage="submitting",
            percent=5,
            message="正在准备解析任务",
            status="Processing",
        )
        doc_path = Path(record.file_path)
        if not doc_path.exists():
            raise FileNotFoundError(f"文档文件不存在: {record.file_path}")

        if backend == "mineru":
            await self._ingest_document_record_with_mineru(db, record, doc_path.read_bytes())
        else:
            await self._ingest_pdf_record(
                db=db,
                record=record,
                contents=doc_path.read_bytes(),
                file_name=record.file_name,
            )

    async def process_pdf_upload(self, db: Session, file: UploadFile) -> DocumentRecord:
        """
        处理 PDF 文档上传：解析文本和图片，分别向量化存储。

        流程：
        1. 保存 PDF 文件到 storage/docs/
        2. 创建 DocumentRecord（status=Processing）
        3. 解析 PDF：提取文本片段 + 图片字节
        4. 文本片段 → DocumentVectorStore（documents_text）
        5. 图片字节 → 逐张调用 ImageDescriptionChain → ChromaVectorStore（images_main_kb）
        6. 更新 DocumentRecord status=Completed

        Args:
            db: 数据库会话
            file: 上传的 PDF 文件

        Returns:
            DocumentRecord: 文档记录
        """
        record, _deduplicated, _duplicate_of = await self.create_document_upload_record(db, file)
        doc_path = Path(record.file_path)

        try:
            await self._process_document_record(db, record)
        except Exception as e:
            self._mark_document_failed(db, doc_id=record.id, error_message=str(e))

        return record

    async def _ingest_pdf_record(
        self,
        db: Session,
        record: DocumentRecord,
        contents: bytes,
        file_name: str,
    ) -> None:
        doc_id = record.id
        doc_path = Path(record.file_path)
        self._set_document_progress(
            db,
            record,
            stage="parsing_text",
            percent=20,
            message="正在解析文本内容",
        )
        text_documents = extract_pdf_text_documents(str(doc_path), file_name=file_name)
        parsed_text_chunks = build_pdf_text_chunks(text_documents, doc_id=doc_id)
        self._set_document_progress(
            db,
            record,
            stage="extracting_images",
            percent=45,
            message="正在提取图片和表格",
        )
        visual_assets = extract_pdf_visual_assets(contents, file_name=file_name)

        if parsed_text_chunks:
            self._set_document_progress(
                db,
                record,
                stage="vectorizing",
                percent=70,
                message="正在写入文本向量",
            )
            self._upsert_document_chunks_with_retry(
                doc_id=doc_id,
                chunks=[chunk.content for chunk in parsed_text_chunks],
                metadatas=[
                    {
                        **chunk.metadata,
                        "enabled": bool(record.enabled),
                        "document_type": record.document_type,
                    }
                    for chunk in parsed_text_chunks
                ],
            )

        processed_image_count = 0
        for idx, asset in enumerate(visual_assets):
            try:
                img_id = str(uuid.uuid4())
                img_bytes = asset.image_bytes
                from app.data.storage import BASE_STORAGE_DIR
                img_dir = BASE_STORAGE_DIR / "custom"
                img_dir.mkdir(parents=True, exist_ok=True)
                img_path = img_dir / f"{img_id}.jpg"
                with open(str(img_path), "wb") as f:
                    f.write(img_bytes)

                img_b64 = base64.b64encode(img_bytes).decode("utf-8")
                description = await self.image_description_chain.ainvoke({"image_b64": img_b64})

                lc_doc = LCDoc(
                    page_content=description,
                    metadata={
                        "id": img_id,
                        "source": record.document_type,
                        "doc_id": doc_id,
                        "file_name": file_name,
                        "file_path": str(img_path),
                        "page_number": asset.page_number,
                        "asset_type": asset.asset_type,
                        "enabled": True,
                        "parent_doc_enabled": bool(record.enabled),
                        "title": f"{file_name} 图片 {processed_image_count + 1}",
                        "tags": [],
                        **{
                            key: value
                            for key, value in asset.metadata.items()
                            if not str(key).startswith("_")
                        },
                    },
                )
                self.vector_store.add_documents([lc_doc], ids=[img_id])

                image_extra_metadata = {
                    "doc_id": doc_id,
                    "page_number": asset.page_number,
                    "asset_type": asset.asset_type,
                    **{
                        key: value
                        for key, value in asset.metadata.items()
                        if not str(key).startswith("_")
                    },
                }
                img_record = ImageRecord(
                    id=img_id,
                    file_path=str(img_path),
                    title=f"{file_name} 图片 {processed_image_count + 1}",
                    generated_description=description,
                    status="Completed",
                    source_dataset=record.document_type,
                    parent_doc_id=doc_id,
                    content_hash=self._compute_content_hash(img_bytes),
                    logical_asset_id=img_id,
                    version_number=1,
                    is_latest=True,
                    extra_metadata=json.dumps(
                        image_extra_metadata,
                        ensure_ascii=False,
                    ),
                )
                db.add(img_record)
                db.commit()

                processed_image_count += 1
                if visual_assets:
                    progress = 75 + int((processed_image_count / max(len(visual_assets), 1)) * 20)
                    self._set_document_progress(
                        db,
                        record,
                        stage="vectorizing",
                        percent=progress,
                        message=f"正在处理图片资产 {processed_image_count}/{len(visual_assets)}",
                    )
            except Exception as exc:
                logger.warning(
                    "[Adapter] PDF 图片处理失败: file=%s index=%s error=%s",
                    file_name,
                    idx,
                    exc,
                )

        record.chunk_count = len(parsed_text_chunks)
        record.image_count = processed_image_count
        record.status = "Completed"
        record.parse_stage = "completed"
        record.progress_percent = 100
        record.progress_message = "解析完成"
        db.commit()
        db.refresh(record)
        self._bm25_add_chunks(doc_id, [chunk.content for chunk in parsed_text_chunks], processed_image_count)

    async def _ingest_document_record_with_mineru(
        self,
        db: Session,
        record: DocumentRecord,
        contents: bytes,
    ) -> None:
        record_id = record.id
        record_file_name = record.file_name
        if not settings.MINERU_API_TOKEN:
            raise ValueError("DOC_PARSE_BACKEND=mineru 时必须配置 MINERU_API_TOKEN")

        client = MinerUClient()
        self._set_document_progress(
            db,
            record,
            stage="submitting",
            percent=10,
            message="正在向 MinerU 提交解析任务",
        )
        batch_id, signed_url = await client.create_upload_task(record_file_name, record_id)
        await client.upload_file(signed_url, contents)
        self._set_document_progress(
            db,
            record,
            stage="uploading",
            percent=20,
            message="文档已提交到 MinerU，等待解析",
        )

        status = None
        while True:
            status = await client.get_batch_result(batch_id, record.file_name)
            if status.state == "done":
                break
            if status.state == "failed":
                raise ValueError(status.err_msg or "MinerU 解析失败")

            progress_percent = 25
            if status.total_pages > 0:
                progress_percent = 25 + int((status.progress_pages / status.total_pages) * 50)
            self._set_document_progress(
                db,
                record,
                stage="parsing_text",
                percent=progress_percent,
                message=f"MinerU 解析中：{status.progress_pages}/{status.total_pages or '?'} 页",
            )
            await asyncio.sleep(max(settings.MINERU_POLL_INTERVAL_SECONDS, 0.5))

        if not status or not status.full_zip_url:
            raise ValueError("MinerU 未返回结果压缩包地址")

        self._set_document_progress(
            db,
            record,
            stage="extracting_images",
            percent=80,
            message="正在下载 MinerU 解析结果",
        )
        result = await client.download_result_zip(status.full_zip_url)
        cleaned_markdown = normalize_mineru_markdown_for_chunking(result.markdown_text)
        artifact_paths = self._persist_mineru_artifacts(
            record=record,
            result=result,
            cleaned_markdown=cleaned_markdown,
        )
        markdown_doc = LCDoc(
            page_content=cleaned_markdown,
            metadata={
                "page_number": 1,
                "file_name": record_file_name,
                "source_type": "pdf_page",
            },
        )
        parsed_text_chunks = build_pdf_text_chunks([markdown_doc], doc_id=record_id)

        self._set_document_progress(
            db,
            record,
            stage="vectorizing",
            percent=88,
            message="正在写入 MinerU 文本结果",
        )
        if parsed_text_chunks:
            self._upsert_document_chunks_with_retry(
                doc_id=record.id,
                chunks=[chunk.content for chunk in parsed_text_chunks],
                metadatas=[
                    {
                        **chunk.metadata,
                        "enabled": bool(record.enabled),
                        "document_type": record.document_type,
                        "parse_backend": "mineru",
                    }
                    for chunk in parsed_text_chunks
                ],
            )

        processed_image_count = 0
        total_images = len(result.images)
        for index, (image_name, image_bytes) in enumerate(result.images, start=1):
            try:
                img_id = str(uuid.uuid4())
                img_dir = BASE_STORAGE_DIR / "custom"
                img_dir.mkdir(parents=True, exist_ok=True)
                suffix = Path(image_name).suffix or ".png"
                img_path = img_dir / f"{img_id}{suffix}"
                with open(str(img_path), "wb") as f:
                    f.write(image_bytes)

                description = await self.image_description_chain.ainvoke(
                    {"image_b64": base64.b64encode(image_bytes).decode("utf-8")}
                )
                lc_doc = LCDoc(
                    page_content=description,
                    metadata={
                        "id": img_id,
                        "source": "pdf",
                        "doc_id": record_id,
                        "file_name": record_file_name,
                        "file_path": str(img_path),
                        "asset_type": "mineru_image",
                        "enabled": True,
                        "parent_doc_enabled": bool(record.enabled),
                        "title": f"{record_file_name} MinerU 图片 {index}",
                        "tags": [],
                    },
                )
                self.vector_store.add_documents([lc_doc], ids=[img_id])
                img_record = ImageRecord(
                    id=img_id,
                    file_path=str(img_path),
                    title=f"{record_file_name} MinerU 图片 {index}",
                    generated_description=description,
                    status="Completed",
                    source_dataset=record.document_type,
                    parent_doc_id=record_id,
                    content_hash=self._compute_content_hash(image_bytes),
                    logical_asset_id=img_id,
                    version_number=1,
                    is_latest=True,
                    extra_metadata=json.dumps(
                        {
                            "doc_id": record_id,
                            "asset_type": "mineru_image",
                            "source_name": image_name,
                        },
                        ensure_ascii=False,
                    ),
                )
                db.add(img_record)
                db.commit()
                processed_image_count += 1
                self._set_document_progress(
                    db,
                    record,
                    stage="vectorizing",
                    percent=88 + int((processed_image_count / max(total_images, 1)) * 10),
                    message=f"正在写入 MinerU 图片结果 {processed_image_count}/{total_images}",
                )
            except Exception as exc:
                db.rollback()
                logger.warning("[Adapter] MinerU 图片处理失败: file=%s index=%s error=%s", record_file_name, index, exc)

        record.chunk_count = len(parsed_text_chunks)
        record.image_count = processed_image_count
        record.status = "Completed"
        record.parse_stage = "completed"
        record.progress_percent = 100
        record.progress_message = "解析完成"
        record.extra_metadata = json.dumps(
            {
                "mineru_batch_id": batch_id,
                "mineru_full_zip_url": status.full_zip_url,
                **artifact_paths,
                **result.raw_metadata,
            },
            ensure_ascii=False,
        )
        db.commit()
        db.refresh(record)
        self._bm25_add_chunks(record.id, [chunk.content for chunk in parsed_text_chunks], processed_image_count)

    def _persist_mineru_artifacts(
        self,
        *,
        record: DocumentRecord,
        result: MinerUParseResult,
        cleaned_markdown: str,
    ) -> Dict[str, str]:
        """将 MinerU 原始产物落到本地，便于核查解析质量。"""
        artifact_dir = DOC_STORAGE_DIR / "mineru" / record.id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        raw_markdown_name = result.markdown_file_name or "full.md"
        raw_markdown_path = artifact_dir / raw_markdown_name
        cleaned_markdown_path = artifact_dir / "full.cleaned.md"
        zip_path = artifact_dir / "result.zip"
        metadata_path = artifact_dir / "metadata.json"

        raw_markdown_path.write_text(result.markdown_text, encoding="utf-8")
        cleaned_markdown_path.write_text(cleaned_markdown, encoding="utf-8")
        zip_path.write_bytes(result.zip_bytes)
        metadata_path.write_text(
            json.dumps(result.raw_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "mineru_artifact_dir": str(artifact_dir),
            "mineru_markdown_path": str(raw_markdown_path),
            "mineru_cleaned_markdown_path": str(cleaned_markdown_path),
            "mineru_zip_path": str(zip_path),
            "mineru_metadata_path": str(metadata_path),
        }

    async def reprocess_image_record(self, db: Session, record: ImageRecord) -> list[str]:
        warnings: list[str] = []
        image_path = Path(record.file_path)
        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {record.file_path}")

        record.status = "Processing"
        db.commit()
        db.refresh(record)

        contents = image_path.read_bytes()
        b64_image = base64.b64encode(contents).decode("utf-8")
        description = await self.image_description_chain.ainvoke({"image_b64": b64_image})

        record.generated_description = description
        record.status = "Completed"
        db.commit()
        db.refresh(record)

        metadata = {
            "id": record.id,
            "file_path": record.file_path,
            "filename": image_path.name,
            "source_dataset": record.source_dataset,
            "title": record.title,
            "tags": load_tags(record.tags),
            "enabled": bool(record.enabled),
            "parent_doc_enabled": True,
        }
        parent_doc_id = record.parent_doc_id or load_json_dict(record.extra_metadata).get("doc_id")
        if isinstance(parent_doc_id, str) and parent_doc_id:
            metadata["doc_id"] = parent_doc_id
            metadata["parent_doc_enabled"] = True
        self.vector_store.upsert_image_description(record.id, description, metadata)
        try:
            self._rebuild_bm25_index()
        except Exception as exc:
            warnings.append(f"BM25 索引重建失败: {exc}")
        return warnings

    async def reprocess_document_record(self, db: Session, record: DocumentRecord) -> list[str]:
        warnings = self.delete_document_record(db, record, preserve_record=True)
        doc_path = Path(record.file_path)
        if not doc_path.exists():
            raise FileNotFoundError(f"文档文件不存在: {record.file_path}")

        record.status = "Processing"
        record.chunk_count = 0
        record.image_count = 0
        db.commit()
        db.refresh(record)

        try:
            await self._ingest_pdf_record(
                db=db,
                record=record,
                contents=doc_path.read_bytes(),
                file_name=record.file_name,
            )
        except Exception as exc:
            record.status = "Failed"
            record.extra_metadata = str(exc)
            db.commit()
            db.refresh(record)
            raise
        try:
            self._rebuild_bm25_index()
        except Exception as exc:
            warnings.append(f"BM25 索引重建失败: {exc}")
        return warnings

    def delete_image_record(self, db: Session, record: ImageRecord) -> list[str]:
        warnings: list[str] = []
        try:
            self.vector_store.delete(ids=[record.id])
        except Exception as exc:
            warnings.append(f"图片向量删除失败: {exc}")

        db.delete(record)
        db.commit()

        try:
            safe_unlink(record.file_path)
        except Exception as exc:
            warnings.append(f"图片文件删除失败: {exc}")

        try:
            self._rebuild_bm25_index()
        except Exception as exc:
            warnings.append(f"BM25 索引重建失败: {exc}")
        return warnings

    def delete_document_record(
        self,
        db: Session,
        record: DocumentRecord,
        *,
        preserve_record: bool = False,
    ) -> list[str]:
        warnings: list[str] = []
        related_images = get_document_image_records(db, record.id)

        try:
            self.document_vector_store.delete_document(record.id)
        except Exception as exc:
            warnings.append(f"文档向量删除失败: {exc}")

        for image_record in related_images:
            try:
                self.vector_store.delete(ids=[image_record.id])
            except Exception as exc:
                warnings.append(f"派生图片向量删除失败: {image_record.id}: {exc}")

        for image_record in related_images:
            db.delete(image_record)

        if not preserve_record:
            db.delete(record)
        db.commit()

        for image_record in related_images:
            try:
                safe_unlink(image_record.file_path)
            except Exception as exc:
                warnings.append(f"派生图片文件删除失败: {image_record.id}: {exc}")

        if not preserve_record:
            try:
                safe_unlink(record.file_path)
            except Exception as exc:
                warnings.append(f"文档文件删除失败: {exc}")

        try:
            self._rebuild_bm25_index()
        except Exception as exc:
            warnings.append(f"BM25 索引重建失败: {exc}")
        return warnings

    def sync_image_record_vector(self, record: ImageRecord, *, parent_doc_enabled: bool = True) -> None:
        """同步单张图片的向量 metadata。"""
        metadata = {
            "id": record.id,
            "file_path": record.file_path,
            "filename": Path(record.file_path).name,
            "source_dataset": record.source_dataset,
            "title": record.title,
            "tags": load_tags(record.tags),
            "enabled": bool(record.enabled),
            "parent_doc_enabled": bool(parent_doc_enabled),
        }
        extra = load_json_dict(record.extra_metadata)
        if record.parent_doc_id:
            metadata["doc_id"] = record.parent_doc_id
        elif extra.get("doc_id"):
            metadata["doc_id"] = extra["doc_id"]
        if extra.get("page_number") is not None:
            metadata["page_number"] = extra["page_number"]
        if extra.get("asset_type"):
            metadata["asset_type"] = extra["asset_type"]
        for key in (
            "table_index_on_page",
            "table_count_on_page",
            "table_group_id",
            "continued_from_previous_page",
            "continued_to_next_page",
            "fallback_reason",
            "related_table_indices",
        ):
            if key in extra:
                metadata[key] = extra[key]
        self.vector_store.upsert_image_description(record.id, record.generated_description or "", metadata)

    def sync_document_record_vectors(self, db: Session, record: DocumentRecord) -> None:
        """同步文档 chunks 与派生图片的启用状态到向量 metadata。"""
        self.document_vector_store.refresh_document_metadata(
            record.id,
            {
                "enabled": bool(record.enabled),
                "document_type": record.document_type,
                "file_name": record.file_name,
            },
        )
        for image_record in get_document_image_records(db, record.id):
            self.sync_image_record_vector(image_record, parent_doc_enabled=bool(record.enabled))


# 全局适配器实例缓存
_adapter: Optional[LangChainAdapter] = None


def get_langchain_adapter() -> LangChainAdapter:
    """
    获取 LangChain 适配器实例（单例模式）

    Returns:
        LangChainAdapter: 适配器实例
    """
    global _adapter
    if _adapter is None:
        _adapter = LangChainAdapter()
    return _adapter
