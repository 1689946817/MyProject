from typing import List

from fastapi import APIRouter, File, UploadFile

from app.application.dispatcher import image_to_image_search, text_to_image_search
from app.application.schemas import (
    ImageSearchResponse,
    SearchResultItem,
    TextSearchRequest,
    TextSearchResponse,
)


router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("/text-to-image", response_model=TextSearchResponse)
async def text_to_image(body: TextSearchRequest) -> TextSearchResponse:
    hits = await text_to_image_search(query=body.query, top_k=body.top_k)
    results: List[SearchResultItem] = []
    for item in hits:
        meta = item.get("metadata") or {}
        results.append(
            SearchResultItem(
                id=item.get("id"),
                file_path=meta.get("file_path"),
                description=item.get("document"),
                score=float(item.get("score", 0.0)),
            )
        )
    return TextSearchResponse(query=body.query, results=results)


@router.post("/image-to-image", response_model=ImageSearchResponse)
async def image_to_image(
    file: UploadFile = File(...),
    top_k: int = 10,
) -> ImageSearchResponse:
    hits, query_desc = await image_to_image_search(file=file, top_k=top_k)
    results: List[SearchResultItem] = []
    for item in hits:
        meta = item.get("metadata") or {}
        results.append(
            SearchResultItem(
                id=item.get("id"),
                file_path=meta.get("file_path"),
                description=item.get("document"),
                score=float(item.get("score", 0.0)),
            )
        )
    return ImageSearchResponse(query_description=query_desc, results=results)

