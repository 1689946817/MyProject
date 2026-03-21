"""
文档知识库 API 路由

提供 PDF 文档的上传、列表查询及解析结果查看接口。
"""
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.application.schemas import (
    DocChunk,
    DocParseResult,
    DocumentRecordOut,
    ImageRecordOut,
    UploadDocumentResponse,
)
from app.data.database import get_db
from app.data.doc_models import DocumentRecord
from app.data.models import ImageRecord
from app.langchain_integration.adapters import get_langchain_adapter

router = APIRouter(prefix="/api/docs", tags=["documents"])


@router.post("/upload", response_model=UploadDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadDocumentResponse:
    """上传 PDF 文档并解析向量化"""
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
    limit: int = 50,
    db: Session = Depends(get_db),
) -> List[DocumentRecordOut]:
    """获取文档记录列表"""
    records = (
        db.query(DocumentRecord)
        .order_by(DocumentRecord.upload_time.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [DocumentRecordOut.model_validate(r) for r in records]


@router.get("/{doc_id}/result", response_model=DocParseResult)
def get_doc_result(
    doc_id: str,
    db: Session = Depends(get_db),
) -> DocParseResult:
    """查看指定文档的解析结果（文本片段 + 提取的图片）"""
    record = db.query(DocumentRecord).filter(DocumentRecord.id == doc_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 查询该文档提取出的图片
    img_records = (
        db.query(ImageRecord)
        .filter(ImageRecord.source_dataset == "pdf")
        .filter(ImageRecord.extra_metadata.contains(doc_id))
        .all()
    )

    # 查询文本片段
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
            chunks.append(DocChunk(
                doc_id=doc_id,
                chunk_index=meta.get("chunk_index", i),
                content=content,
                score=0.0,
            ))
        # 按 chunk_index 排序
        chunks.sort(key=lambda c: c.chunk_index)
    except Exception:
        pass

    return DocParseResult(
        document=DocumentRecordOut.model_validate(record),
        chunks=chunks,
        images=[ImageRecordOut.model_validate(r) for r in img_records],
    )
