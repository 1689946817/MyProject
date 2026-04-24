"""文档知识库 API 路由。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.application.knowledge_management import (
    dump_json_dict,
    dump_tags,
    ensure_knowledge_management_columns,
    get_document_image_records,
    get_document_record_or_raise,
    validate_document_type,
)
from app.application.operations import create_job
from app.application.schemas import (
    DeleteResponse,
    DocChunk,
    DocParseResult,
    DocumentProgressResponse,
    DocumentRecordOut,
    DocumentRecordUpdateRequest,
    ImageRecordOut,
    JobTaskOut,
    TimingSummary,
    UploadDocumentResponse,
)
from app.core.config import settings
from app.core.timing import RequestTimingCollector, bind_timing_collector
from app.data.database import get_db
from app.data.doc_models import DocumentRecord
from app.data.ops_models import JobTask
from app.langchain_integration.adapters import get_langchain_adapter

router = APIRouter(prefix="/api/docs", tags=["documents"])
SEARCH_KEYWORD_MAX_LENGTH = 4000


@router.post("/upload", response_model=UploadDocumentResponse, response_model_exclude_none=True)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadDocumentResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    collector = RequestTimingCollector("/api/docs/upload", "document_upload")
    collector.set_metadata(filename=file.filename)
    response: UploadDocumentResponse | None = None
    try:
        with bind_timing_collector(collector), collector.stage("document_upload_total"):
            adapter = get_langchain_adapter()
            record, deduplicated, duplicate_of = await adapter.create_document_upload_record(db=db, file=file)
            job = None
            if not deduplicated:
                job = create_job(
                    db,
                    job_type="document_parse",
                    payload={"doc_id": record.id},
                    related_doc_id=record.id,
                )
            response = UploadDocumentResponse(
                document=DocumentRecordOut.model_validate(
                    {
                        **DocumentRecordOut.model_validate(record).model_dump(),
                        "deduplicated": deduplicated,
                        "duplicate_of": duplicate_of,
                    }
                ),
                job=JobTaskOut.model_validate(job) if job is not None else None,
                message="文档重复，已复用现有记录" if deduplicated else "文档已上传，正在后台解析",
            )
        if settings.EXPOSE_TIMINGS_IN_API and response is not None:
            response.timings = TimingSummary.model_validate(collector.snapshot())
        return response
    finally:
        collector.finish(log_enabled=settings.ENABLE_TIMING_LOGS)


@router.get("/list", response_model=List[DocumentRecordOut])
def list_documents(
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    keyword: Optional[str] = Query(default=None, max_length=SEARCH_KEYWORD_MAX_LENGTH),
    status: Optional[str] = Query(default=None, max_length=30),
    enabled: Optional[bool] = None,
    document_type: Optional[str] = Query(default=None, max_length=50),
    tag: Optional[str] = Query(default=None, max_length=50),
    include_history: bool = False,
    db: Session = Depends(get_db),
) -> List[DocumentRecordOut]:
    ensure_knowledge_management_columns(db)
    query = db.query(DocumentRecord)
    if not include_history:
        query = query.filter(DocumentRecord.is_latest.is_(True))
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (DocumentRecord.file_name.like(like))
            | (DocumentRecord.title.like(like))
            | (DocumentRecord.notes.like(like))
        )
    if status:
        query = query.filter(DocumentRecord.status == status)
    if enabled is not None:
        query = query.filter(DocumentRecord.enabled == enabled)
    if document_type:
        query = query.filter(DocumentRecord.document_type == document_type)
    if tag:
        query = query.filter(DocumentRecord.tags.like(f"%{tag}%"))

    records = query.order_by(DocumentRecord.upload_time.desc()).offset(skip).limit(limit).all()
    return [DocumentRecordOut.model_validate(r) for r in records]


@router.get("/{doc_id}/versions", response_model=List[DocumentRecordOut])
def list_document_versions(doc_id: str, db: Session = Depends(get_db)) -> List[DocumentRecordOut]:
    try:
        record = get_document_record_or_raise(db, doc_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logical_asset_id = record.logical_asset_id or record.id
    versions = (
        db.query(DocumentRecord)
        .filter(DocumentRecord.logical_asset_id == logical_asset_id)
        .order_by(DocumentRecord.version_number.desc(), DocumentRecord.upload_time.desc())
        .all()
    )
    return [DocumentRecordOut.model_validate(item) for item in versions]


@router.post("/{doc_id}/versions", response_model=UploadDocumentResponse, response_model_exclude_none=True)
async def upload_document_new_version(
    doc_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadDocumentResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")
    try:
        current = get_document_record_or_raise(db, doc_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    collector = RequestTimingCollector("/api/docs/{doc_id}/versions", "document_upload_new_version")
    collector.set_metadata(filename=file.filename, logical_asset_id=current.logical_asset_id or current.id)
    response: UploadDocumentResponse | None = None
    try:
        with bind_timing_collector(collector), collector.stage("document_upload_new_version_total"):
            record, deduplicated, duplicate_of = await get_langchain_adapter().create_document_upload_record(
                db=db,
                file=file,
                logical_asset_id=current.logical_asset_id or current.id,
            )
            job = None
            if not deduplicated:
                job = create_job(
                    db,
                    job_type="document_parse",
                    payload={"doc_id": record.id},
                    related_doc_id=record.id,
                )
            response = UploadDocumentResponse(
                document=DocumentRecordOut.model_validate(
                    {
                        **DocumentRecordOut.model_validate(record).model_dump(),
                        "deduplicated": deduplicated,
                        "duplicate_of": duplicate_of,
                    }
                ),
                job=JobTaskOut.model_validate(job) if job is not None else None,
                message="文档版本重复，已复用现有记录" if deduplicated else "文档新版本已上传，正在后台解析",
            )
        if settings.EXPOSE_TIMINGS_IN_API and response is not None:
            response.timings = TimingSummary.model_validate(collector.snapshot())
        return response
    finally:
        collector.finish(log_enabled=settings.ENABLE_TIMING_LOGS)


@router.get("/{doc_id}", response_model=DocumentRecordOut)
def get_document_detail(
    doc_id: str,
    db: Session = Depends(get_db),
) -> DocumentRecordOut:
    try:
        record = get_document_record_or_raise(db, doc_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DocumentRecordOut.model_validate(record)


@router.patch("/{doc_id}", response_model=DocumentRecordOut)
def update_document(
    doc_id: str,
    payload: DocumentRecordUpdateRequest,
    db: Session = Depends(get_db),
) -> DocumentRecordOut:
    try:
        record = get_document_record_or_raise(db, doc_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    enabled_changed = payload.enabled is not None and payload.enabled != bool(record.enabled)

    if payload.title is not None:
        record.title = payload.title.strip() or None
    if payload.tags is not None:
        record.tags = dump_tags(payload.tags)
    if payload.notes is not None:
        record.notes = payload.notes.strip() or None
    if payload.enabled is not None:
        record.enabled = payload.enabled
    if payload.document_type is not None:
        try:
            record.document_type = validate_document_type(payload.document_type) or "pdf"
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.custom_metadata is not None:
        record.custom_metadata = dump_json_dict(payload.custom_metadata)

    db.add(record)
    db.commit()
    db.refresh(record)
    get_langchain_adapter().sync_document_record_vectors(db, record)
    if enabled_changed:
        get_langchain_adapter()._rebuild_bm25_index()
    return DocumentRecordOut.model_validate(record)


@router.delete("/{doc_id}", response_model=DeleteResponse)
def delete_document(
    doc_id: str,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> DeleteResponse:
    if not confirm:
        raise HTTPException(status_code=400, detail="删除文档需要 confirm=true")
    try:
        record = get_document_record_or_raise(db, doc_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    warnings = get_langchain_adapter().delete_document_record(db, record)
    return DeleteResponse(success=True, message="文档已删除", warnings=warnings)


@router.post("/{doc_id}/reprocess", response_model=DeleteResponse)
async def reprocess_document(
    doc_id: str,
    db: Session = Depends(get_db),
) -> DeleteResponse:
    try:
        record = get_document_record_or_raise(db, doc_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    record.status = "Processing"
    record.parse_stage = "queued"
    record.progress_percent = 0
    record.progress_message = "文档已加入重新解析队列"
    db.add(record)
    db.commit()
    db.refresh(record)
    create_job(
        db,
        job_type="document_reprocess",
        payload={"doc_id": record.id},
        related_doc_id=record.id,
    )
    return DeleteResponse(success=True, message="文档已加入重新解析队列", warnings=[])


@router.get("/{doc_id}/progress", response_model=DocumentProgressResponse)
def get_document_progress(
    doc_id: str,
    db: Session = Depends(get_db),
) -> DocumentProgressResponse:
    try:
        record = get_document_record_or_raise(db, doc_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    collector = RequestTimingCollector("/api/docs/{doc_id}/progress", "document_progress")
    try:
        with bind_timing_collector(collector), collector.stage("document_progress_total"):
            job = (
                db.query(JobTask)
                .filter(JobTask.related_doc_id == doc_id)
                .order_by(JobTask.created_at.desc())
                .first()
            )
            return DocumentProgressResponse(
                document=DocumentRecordOut.model_validate(record),
                status=record.status,
                stage=getattr(record, "parse_stage", "queued") or "queued",
                progress_percent=int(getattr(record, "progress_percent", 0) or 0),
                message=getattr(record, "progress_message", None),
                job=JobTaskOut.model_validate(job) if job is not None else None,
                timings=TimingSummary.model_validate(collector.snapshot()) if settings.EXPOSE_TIMINGS_IN_API else None,
            )
    finally:
        collector.finish(log_enabled=settings.ENABLE_TIMING_LOGS)


@router.get("/{doc_id}/result", response_model=DocParseResult)
def get_doc_result(
    doc_id: str,
    db: Session = Depends(get_db),
) -> DocParseResult:
    try:
        record = get_document_record_or_raise(db, doc_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    img_records = get_document_image_records(db, doc_id)

    chunks: List[DocChunk] = []
    try:
        from app.langchain_integration.vectorstores import get_document_vector_store

        doc_vs = get_document_vector_store()
        collection = doc_vs._vectorstore._collection
        results = collection.get(
            where={"doc_id": doc_id},
            include=["documents", "metadatas"],
        )
        docs_list = results.get("documents") or []
        metas_list = results.get("metadatas") or []
        for i, content in enumerate(docs_list):
            meta = metas_list[i] if i < len(metas_list) else {}
            chunks.append(
                DocChunk(
                    doc_id=doc_id,
                    chunk_index=meta.get("chunk_index", i),
                    content=content,
                    score=0.0,
                    page_number=meta.get("page_number"),
                    source_type=meta.get("source_type"),
                )
            )
        chunks.sort(key=lambda c: c.chunk_index)
    except Exception:
        pass

    collector = RequestTimingCollector("/api/docs/{doc_id}/result", "document_result")
    try:
        with bind_timing_collector(collector), collector.stage("document_result_total"):
            return DocParseResult(
                document=DocumentRecordOut.model_validate(record),
                chunks=chunks,
                images=[ImageRecordOut.model_validate(r) for r in img_records],
                timings=TimingSummary.model_validate(collector.snapshot()) if settings.EXPOSE_TIMINGS_IN_API else None,
            )
    finally:
        collector.finish(log_enabled=settings.ENABLE_TIMING_LOGS)
