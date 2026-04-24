"""任务队列、批量导入与反馈相关路由。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.application.operations import (
    create_import_batch,
    create_job,
    get_import_batch_or_raise,
    get_job_or_raise,
    list_jobs,
    refresh_import_batch_summary,
    retry_job,
)
from app.application.schemas import BatchImportResponse, DocumentRecordOut, ImportBatchOut, JobTaskOut, TimingSummary
from app.core.config import settings
from app.core.timing import RequestTimingCollector, bind_timing_collector
from app.data.database import get_db
from app.langchain_integration.adapters import get_langchain_adapter


router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs", response_model=List[JobTaskOut])
def list_jobs_endpoint(
    status: Optional[str] = Query(default=None, max_length=30),
    job_type: Optional[str] = Query(default=None, max_length=50),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[JobTaskOut]:
    jobs = list_jobs(db, status=status, job_type=job_type, limit=limit, offset=offset)
    return [JobTaskOut.model_validate(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=JobTaskOut)
def get_job_endpoint(job_id: str, db: Session = Depends(get_db)) -> JobTaskOut:
    try:
        job = get_job_or_raise(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JobTaskOut.model_validate(job)


@router.post("/jobs/{job_id}/retry", response_model=JobTaskOut)
def retry_job_endpoint(job_id: str, db: Session = Depends(get_db)) -> JobTaskOut:
    try:
        job = get_job_or_raise(db, job_id)
        retried = retry_job(db, job)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobTaskOut.model_validate(retried)


@router.post("/imports/batch", response_model=BatchImportResponse, response_model_exclude_none=True)
async def batch_import_documents(
    files: List[UploadFile] = File(...),
    source_type: str = Form("document"),
    db: Session = Depends(get_db),
) -> BatchImportResponse:
    collector = RequestTimingCollector("/api/imports/batch", "batch_import")
    collector.set_metadata(file_count=len(files), source_type=source_type)
    response: BatchImportResponse | None = None
    try:
        with bind_timing_collector(collector), collector.stage("batch_import_total"):
            adapter = get_langchain_adapter()
            batch = create_import_batch(db, source_type=source_type)
            jobs = []
            documents = []
            for file in files:
                if not file.filename or not file.filename.lower().endswith(".pdf"):
                    continue
                record, deduplicated, duplicate_of = await adapter.create_document_upload_record(db=db, file=file)
                job = create_job(
                    db,
                    job_type="document_parse",
                    payload={"doc_id": record.id},
                    related_doc_id=record.id,
                    related_batch_id=batch.id,
                )
                jobs.append(job)
                documents.append(
                    DocumentRecordOut.model_validate(
                        {
                            **DocumentRecordOut.model_validate(record).model_dump(),
                            "deduplicated": deduplicated,
                            "duplicate_of": duplicate_of,
                        }
                    )
                )
            refreshed = refresh_import_batch_summary(db, batch)
            response = BatchImportResponse(
                batch=ImportBatchOut.model_validate(refreshed),
                jobs=[JobTaskOut.model_validate(job) for job in jobs],
                documents=documents,
                message="批量导入任务已创建",
            )
        if settings.EXPOSE_TIMINGS_IN_API and response is not None:
            response.timings = TimingSummary.model_validate(collector.snapshot())
        return response
    finally:
        collector.finish(log_enabled=settings.ENABLE_TIMING_LOGS)


@router.get("/imports/{batch_id}", response_model=ImportBatchOut)
def get_import_batch_endpoint(batch_id: str, db: Session = Depends(get_db)) -> ImportBatchOut:
    try:
        batch = get_import_batch_or_raise(db, batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    refreshed = refresh_import_batch_summary(db, batch)
    return ImportBatchOut.model_validate(refreshed)
