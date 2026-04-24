"""图片知识库管理 API。"""
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
SEARCH_KEYWORD_MAX_LENGTH = 4000


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


@router.get("/{image_id}/versions", response_model=List[ImageRecordOut])
async def list_image_versions(
    image_id: str,
    db: Session = Depends(get_db),
) -> List[ImageRecordOut]:
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
