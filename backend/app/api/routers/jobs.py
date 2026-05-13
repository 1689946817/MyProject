"""
任务队列、批量导入与反馈相关路由。

本模块封装了后台任务生命周期管理和文档批量导入功能，是前端"任务面板"
与"文档上传"功能的后端入口。

功能分两大块：

1. **任务查询与重试**（JobTask）：
   - 列表查询：支持按状态（status）和类型（job_type）筛选，分页浏览。
   - 单条查询：根据 job_id 获取任务详情。
   - 失败重试：对 status="failed" 的任务重新入队执行。

2. **文档批量导入**（ImportBatch）：
   - 接收多个 PDF 文件上传，创建 ImportBatch 记录并为每个文件生成
     document_parse 类型的 JobTask。
   - 支持文件去重：同一文件不会重复入库。
   - 返回批次摘要（包含关联的 jobs 列表与文档记录）。

所有端点通过 SQLAlchemy 会话访问数据库，并借助 LangChainAdapter
完成文档上传记录与内容解析任务的创建。
"""
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

# ---------------------------------------------------------------------------
# 路由注册
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["jobs"])


# ---------------------------------------------------------------------------
# 任务查询与重试
# ---------------------------------------------------------------------------

@router.get("/jobs", response_model=List[JobTaskOut])
def list_jobs_endpoint(
    status: Optional[str] = Query(default=None, max_length=30),
    job_type: Optional[str] = Query(default=None, max_length=50),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[JobTaskOut]:
    """分页查询任务列表。

    支持按状态和类型进行可选过滤。结果按创建时间倒序排列。

    Args:
        status: 可选的状态过滤条件，如 "pending"、"running"、"completed"、"failed"。
        job_type: 可选的任务类型过滤条件，如 "document_parse"、"image_embed"。
        limit: 每页返回的最大条数，上限 200。
        offset: 分页偏移量，从第 offset 条开始返回。
        db: 数据库会话（依赖注入）。

    Returns:
        符合条件的任务列表，每个任务以 JobTaskOut 序列化返回。
    """
    jobs = list_jobs(db, status=status, job_type=job_type, limit=limit, offset=offset)
    return [JobTaskOut.model_validate(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=JobTaskOut)
def get_job_endpoint(job_id: str, db: Session = Depends(get_db)) -> JobTaskOut:
    """获取指定任务的详情。

    Args:
        job_id: 任务的 UUID 标识符。
        db: 数据库会话（依赖注入）。

    Returns:
        单个任务的完整信息（JobTaskOut）。

    Raises:
        HTTPException(404): 任务不存在时抛出。
    """
    try:
        job = get_job_or_raise(db, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JobTaskOut.model_validate(job)


@router.post("/jobs/{job_id}/retry", response_model=JobTaskOut)
def retry_job_endpoint(job_id: str, db: Session = Depends(get_db)) -> JobTaskOut:
    """重试一个已失败的任务。

    仅允许对 status="failed" 的任务执行重试操作。成功后会创建新的任务记录
    （保留原任务不变），并将新任务入队等待 Worker 调度执行。

    Args:
        job_id: 待重试任务的 UUID 标识符。
        db: 数据库会话（依赖注入）。

    Returns:
        新创建的重试任务信息（JobTaskOut）。

    Raises:
        HTTPException(404): 原任务不存在时抛出。
        HTTPException(400): 原任务状态不允许重试时抛出（如 status != "failed"）。
    """
    try:
        job = get_job_or_raise(db, job_id)
        retried = retry_job(db, job)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobTaskOut.model_validate(retried)


# ---------------------------------------------------------------------------
# 文档批量导入
# ---------------------------------------------------------------------------

@router.post("/imports/batch", response_model=BatchImportResponse, response_model_exclude_none=True)
async def batch_import_documents(
    files: List[UploadFile] = File(...),
    source_type: str = Form("document"),
    db: Session = Depends(get_db),
) -> BatchImportResponse:
    """批量上传 PDF 文件并创建解析任务。

    流程：
    1. 创建一个 ImportBatch 记录作为本次批次的容器。
    2. 遍历上传的文件，过滤非 PDF 文件后逐一：
       - 调用 adapter 创建文档上传记录（含去重检测）。
       - 为每个文档创建一个 "document_parse" 类型的 JobTask。
    3. 刷新批次摘要（统计关联的文档与任务数量）。
    4. 如开启 EXPOSE_TIMINGS_IN_API，将耗时明细附加到响应中。

    Args:
        files: 上传的文件列表（通过 multipart/form-data 提交）。
        source_type: 数据源类型标识，默认 "document"，可扩展为其他业务线。
        db: 数据库会话（依赖注入）。

    Returns:
        BatchImportResponse，包含批次信息、任务列表、文档记录以及提示消息。
        当 EXPOSE_TIMINGS_IN_API 开启时，额外包含 timings 耗时明细。
    """
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
    """获取指定导入批次的详情。

    返回批次信息前会自动刷新摘要（重新统计关联任务的完成/失败数量），
    确保前端看到的进度数据是最新的。

    Args:
        batch_id: 导入批次的 UUID 标识符。
        db: 数据库会话（依赖注入）。

    Returns:
        ImportBatchOut，包含批次元数据、关联任务统计等信息。

    Raises:
        HTTPException(404): 批次不存在时抛出。
    """
    try:
        batch = get_import_batch_or_raise(db, batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    refreshed = refresh_import_batch_summary(db, batch)
    return ImportBatchOut.model_validate(refreshed)
