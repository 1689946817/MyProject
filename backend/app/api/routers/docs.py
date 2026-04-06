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
from app.application.schemas import (
    DeleteResponse,
    DocChunk,
    DocParseResult,
    DocumentRecordOut,
    DocumentRecordUpdateRequest,
    ImageRecordOut,
    UploadDocumentResponse,
)
from app.data.database import get_db
from app.data.doc_models import DocumentRecord
from app.langchain_integration.adapters import get_langchain_adapter

router = APIRouter(prefix="/api/docs", tags=["documents"])


@router.post("/upload", response_model=UploadDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadDocumentResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    adapter = get_langchain_adapter()
    record = await adapter.process_pdf_upload(db=db, file=file)
    return UploadDocumentResponse(
        document=DocumentRecordOut.model_validate(record),
        message=f"解析完成：{record.chunk_count} 个文本片段，{record.image_count} 张图片",
    )


@router.get("/list", response_model=List[DocumentRecordOut])
def list_documents(
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    keyword: Optional[str] = Query(default=None, max_length=100),
    status: Optional[str] = Query(default=None, max_length=30),
    enabled: Optional[bool] = None,
    document_type: Optional[str] = Query(default=None, max_length=50),
    tag: Optional[str] = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
) -> List[DocumentRecordOut]:
    ensure_knowledge_management_columns(db)
    query = db.query(DocumentRecord)
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

    try:
        warnings = await get_langchain_adapter().reprocess_document_record(db, record)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文档重处理失败: {exc}") from exc
    return DeleteResponse(success=True, message="文档已重新解析", warnings=warnings)


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
                )
            )
        chunks.sort(key=lambda c: c.chunk_index)
    except Exception:
        pass

    return DocParseResult(
        document=DocumentRecordOut.model_validate(record),
        chunks=chunks,
        images=[ImageRecordOut.model_validate(r) for r in img_records],
    )
