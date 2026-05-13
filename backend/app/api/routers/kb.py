"""
图片知识库管理 API 路由。

提供图片知识库的 CRUD 操作，包括：
- 图片列表查询：支持按关键词、状态、启用标记、数据来源、标签等多维度过滤
- 图片上传：通过 MLLM 生成结构化描述后存入向量库
- 图片版本管理：支持上传新版本、查看历史版本
- 图片元数据编辑：标题、标签、备注、启用状态、自定义元数据
- 图片删除与重处理

所有路由以 /api/knowledge-base 为前缀。图片处理核心逻辑委托给 LangChainAdapter。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.application.knowledge_management import (
    dump_json_dict,
    dump_tags,
    ensure_knowledge_management_columns,
    get_image_record_or_raise,
)
from app.application.schemas import (
    DeleteResponse,
    ImageRecordOut,
    ImageRecordUpdateRequest,
    TimingSummary,
    UploadImagesResponse,
)
from app.core.config import settings
from app.core.timing import RequestTimingCollector, bind_timing_collector
from app.data.database import get_db
from app.data.models import ImageRecord
from app.langchain_integration.adapters import get_langchain_adapter


router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])
SEARCH_KEYWORD_MAX_LENGTH = 4000  # 搜索关键词最大长度


# ---- 图片列表与查询 ----

@router.get("/list", response_model=List[ImageRecordOut])
async def list_images(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=100, le=200),
    keyword: Optional[str] = Query(default=None, max_length=SEARCH_KEYWORD_MAX_LENGTH),
    status: Optional[str] = Query(default=None, max_length=30),
    enabled: Optional[bool] = None,
    source_dataset: Optional[str] = Query(default=None, max_length=100),
    tag: Optional[str] = Query(default=None, max_length=50),
    include_history: bool = False,
) -> List[ImageRecordOut]:
    """分页查询图片列表，支持按关键词、状态、启用标记、数据来源、标签等多维度过滤。"""
    ensure_knowledge_management_columns(db)
    query = db.query(ImageRecord)
    if not include_history:
        query = query.filter(ImageRecord.is_latest.is_(True))
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (ImageRecord.id.like(like))
            | (ImageRecord.title.like(like))
            | (ImageRecord.generated_description.like(like))
            | (ImageRecord.file_path.like(like))
        )
    if status:
        query = query.filter(ImageRecord.status == status)
    if enabled is not None:
        query = query.filter(ImageRecord.enabled == enabled)
    if source_dataset:
        query = query.filter(ImageRecord.source_dataset == source_dataset)
    if tag:
        query = query.filter(ImageRecord.tags.like(f"%{tag}%"))

    records = query.order_by(ImageRecord.upload_time.desc()).offset(skip).limit(limit).all()
    return [ImageRecordOut.model_validate(r) for r in records]


# ---- 图片版本管理 ----

@router.get("/{image_id}/versions", response_model=List[ImageRecordOut])
async def list_image_versions(
    image_id: str,
    db: Session = Depends(get_db),
) -> List[ImageRecordOut]:
    """查询指定图片的所有历史版本，按版本号降序排列。"""
    try:
        record = get_image_record_or_raise(db, image_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logical_asset_id = record.logical_asset_id or record.id
    versions = (
        db.query(ImageRecord)
        .filter(ImageRecord.logical_asset_id == logical_asset_id)
        .order_by(ImageRecord.version_number.desc(), ImageRecord.upload_time.desc())
        .all()
    )
    return [ImageRecordOut.model_validate(item) for item in versions]


@router.post("/{image_id}/versions", response_model=UploadImagesResponse, response_model_exclude_none=True)
async def upload_image_new_version(
    image_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadImagesResponse:
    """为指定图片上传新版本，复用原图片的数据来源和逻辑资产 ID，自动调用 MLLM 生成描述并存入向量库。

    Args:
        image_id: 要上传新版本的图片记录 ID。
        file: 待上传的图片文件。
        db: SQLAlchemy 数据库会话。

    Returns:
        UploadImagesResponse，包含新版本图片记录及去重信息，可选附带耗时统计。
    """
    try:
        current = get_image_record_or_raise(db, image_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    collector = RequestTimingCollector("/api/knowledge-base/{image_id}/versions", "knowledge_base_upload_new_version")
    collector.set_metadata(filename=file.filename, logical_asset_id=current.logical_asset_id or current.id)
    response: UploadImagesResponse | None = None
    try:
        with bind_timing_collector(collector), collector.stage("knowledge_base_upload_new_version_total"):
            record, _description, deduplicated, duplicate_of = await get_langchain_adapter().process_image_upload(
                db=db,
                file=file,
                split="custom",
                source_dataset=current.source_dataset,
                logical_asset_id=current.logical_asset_id or current.id,
            )
            response = UploadImagesResponse(
                images=[
                    ImageRecordOut.model_validate(
                        {
                            **ImageRecordOut.model_validate(record).model_dump(),
                            "deduplicated": deduplicated,
                            "duplicate_of": duplicate_of,
                        }
                    )
                ],
                deduplicated_count=1 if deduplicated else 0,
            )
        if settings.EXPOSE_TIMINGS_IN_API and response is not None:
            response.timings = TimingSummary.model_validate(collector.snapshot())
        return response
    finally:
        collector.finish(log_enabled=settings.ENABLE_TIMING_LOGS)


@router.get("/{image_id}", response_model=ImageRecordOut)
async def get_image_detail(
    image_id: str,
    db: Session = Depends(get_db),
) -> ImageRecordOut:
    """获取指定图片记录的详细信息。

    Args:
        image_id: 图片记录 ID。
        db: SQLAlchemy 数据库会话。

    Returns:
        ImageRecordOut，包含图片完整元数据。
    """
    try:
        record = get_image_record_or_raise(db, image_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ImageRecordOut.model_validate(record)


@router.patch("/{image_id}", response_model=ImageRecordOut)
async def update_image(
    image_id: str,
    payload: ImageRecordUpdateRequest,
    db: Session = Depends(get_db),
) -> ImageRecordOut:
    """更新指定图片的元数据，包括标题、标签、备注、启用状态、数据来源和自定义元数据。

    更新后自动同步向量库中对应的记录；若启用状态发生变化，还会重建 BM25 索引。

    Args:
        image_id: 图片记录 ID。
        payload: 包含待更新字段的请求体，各字段均为可选。
        db: SQLAlchemy 数据库会话。

    Returns:
        ImageRecordOut，更新后的图片完整元数据。
    """
    try:
        record = get_image_record_or_raise(db, image_id)
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
    if payload.source_dataset is not None:
        record.source_dataset = payload.source_dataset.strip() or None
    if payload.custom_metadata is not None:
        record.custom_metadata = dump_json_dict(payload.custom_metadata)

    db.add(record)
    db.commit()
    db.refresh(record)
    get_langchain_adapter().sync_image_record_vector(record)
    if enabled_changed:
        get_langchain_adapter()._rebuild_bm25_index()
    return ImageRecordOut.model_validate(record)


@router.delete("/{image_id}", response_model=DeleteResponse)
async def delete_image(
    image_id: str,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> DeleteResponse:
    """删除指定图片记录及其对应的向量数据和存储文件。

    需要传入 confirm=true 以确认删除操作，防止误删。

    Args:
        image_id: 图片记录 ID。
        confirm: 是否确认删除，必须为 True 才执行删除。
        db: SQLAlchemy 数据库会话。

    Returns:
        DeleteResponse，包含操作是否成功及可能的警告信息。
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="删除图片需要 confirm=true")

    try:
        record = get_image_record_or_raise(db, image_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    warnings = get_langchain_adapter().delete_image_record(db, record)
    return DeleteResponse(success=True, message="图片已删除", warnings=warnings)


@router.post("/{image_id}/reprocess", response_model=DeleteResponse)
async def reprocess_image(
    image_id: str,
    db: Session = Depends(get_db),
) -> DeleteResponse:
    """重新处理指定图片：删除旧的向量记录，重新调用 MLLM 生成描述并写入向量库。

    适用于图片描述质量不佳或模型升级后需要重新生成描述的场景。

    Args:
        image_id: 图片记录 ID。
        db: SQLAlchemy 数据库会话。

    Returns:
        DeleteResponse，包含操作是否成功及可能的警告信息。
    """
    try:
        record = get_image_record_or_raise(db, image_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        warnings = await get_langchain_adapter().reprocess_image_record(db, record)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图片重处理失败: {exc}") from exc
    return DeleteResponse(success=True, message="图片已重新处理", warnings=warnings)


@router.post("/upload", response_model=UploadImagesResponse, response_model_exclude_none=True)
async def upload_images(
    files: List[UploadFile] = File(...),
    split: str = "custom",
    source_dataset: Optional[str] = None,
    db: Session = Depends(get_db),
) -> UploadImagesResponse:
    """批量上传图片到知识库，对每张图片调用 MLLM 生成结构化描述并存入向量库。

    支持去重检测：若图片已存在则跳过处理并记录去重信息。

    Args:
        files: 待上传的图片文件列表。
        split: 数据分割标识，默认 "custom"。
        source_dataset: 数据来源名称，可选。
        db: SQLAlchemy 数据库会话。

    Returns:
        UploadImagesResponse，包含所有图片记录及去重统计，可选附带耗时统计。
    """
    collector = RequestTimingCollector("/api/knowledge-base/upload", "knowledge_base_upload")
    collector.set_metadata(file_count=len(files), split=split)
    response: UploadImagesResponse | None = None
    try:
        with bind_timing_collector(collector), collector.stage(
            "knowledge_base_upload_total",
            meta={"file_count": len(files), "split": split},
        ):
            adapter = get_langchain_adapter()
            processed = await adapter.process_image_uploads(
                db=db,
                files=files,
                split=split,
                source_dataset=source_dataset,
            )
            records = []
            deduplicated_count = 0
            for rec, _desc, deduplicated, duplicate_of in processed:
                if deduplicated:
                    deduplicated_count += 1
                records.append(
                    ImageRecordOut.model_validate(
                        {
                            **ImageRecordOut.model_validate(rec).model_dump(),
                            "deduplicated": deduplicated,
                            "duplicate_of": duplicate_of,
                        }
                    )
                )
            response = UploadImagesResponse(
                images=records,
                deduplicated_count=deduplicated_count,
            )
        if settings.EXPOSE_TIMINGS_IN_API and response is not None:
            response.timings = TimingSummary.model_validate(collector.snapshot())
        return response
    finally:
        collector.finish(log_enabled=settings.ENABLE_TIMING_LOGS)
