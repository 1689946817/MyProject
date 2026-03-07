from typing import List, Optional

from fastapi import APIRouter, File, Form, UploadFile

from app.application.rag_engine import rag_chat
from app.application.schemas import ChatResponse, SearchResultItem


router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/chat", response_model=ChatResponse)
async def rag_chat_endpoint(
    query: str = Form(...),
    top_k: int = Form(5),
    image: Optional[UploadFile] = File(None),
) -> ChatResponse:
    answer, retrieved = await rag_chat(query=query, top_k=top_k, image=image)
    results: List[SearchResultItem] = []
    for item in retrieved:
        meta = item.get("metadata") or {}
        results.append(
            SearchResultItem(
                id=item.get("id"),
                file_path=meta.get("file_path"),
                description=item.get("document"),
                score=float(item.get("score", 0.0)),
            )
        )
    return ChatResponse(answer=answer, results=results)

