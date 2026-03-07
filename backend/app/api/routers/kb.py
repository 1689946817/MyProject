from typing import List, Optional

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.application.schemas import ImageRecordOut, UploadImagesResponse
from app.data.database import get_db
from app.semantic.description_service import process_image_uploads


router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])


@router.post("/upload", response_model=UploadImagesResponse)
async def upload_images(
    files: List[UploadFile] = File(...),
    split: str = "custom",
    source_dataset: Optional[str] = None,
    db: Session = Depends(get_db),
) -> UploadImagesResponse:
    processed = await process_image_uploads(
        db=db,
        files=files,
        split=split,  # type: ignore[arg-type]
        source_dataset=source_dataset,
    )
    records = [rec for rec, _desc in processed]
    return UploadImagesResponse(images=[ImageRecordOut.from_orm(r) for r in records])

