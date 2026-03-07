from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class ImageRecordOut(BaseModel):
    id: str
    file_path: str
    upload_time: datetime
    generated_description: Optional[str] = None
    status: str
    source_dataset: Optional[str] = None

    class Config:
        orm_mode = True


class UploadImagesResponse(BaseModel):
    images: List[ImageRecordOut]


class SearchResultItem(BaseModel):
    id: str
    file_path: Optional[str] = None
    description: Optional[str] = None
    score: float


class TextSearchRequest(BaseModel):
    query: str
    top_k: int = 10


class TextSearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem]


class ImageSearchResponse(BaseModel):
    query_description: str
    results: List[SearchResultItem]


class ChatResponse(BaseModel):
    answer: str
    results: List[SearchResultItem]

