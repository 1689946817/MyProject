"""
知识库管理 API 路由模块（LangChain 版本）

该模块定义了知识库管理相关的 API 路由，包括：
- 获取已上传的图片记录列表
- 上传图片并生成描述

使用 LangChain 框架实现，所有路由都以 /api/knowledge-base 为前缀。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.application.schemas import ImageRecordOut, UploadImagesResponse
from app.data.database import get_db
from app.data.models import ImageRecord
from app.langchain_integration.adapters import get_langchain_adapter


# 创建 API 路由器，设置前缀和标签
router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])


@router.get("/list", response_model=List[ImageRecordOut])
async def list_images(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> List[ImageRecordOut]:
    """获取已上传的图片记录列表
    
    按上传时间倒序返回图片记录，支持分页。
    
    Args:
        db: 数据库会话，通过依赖注入获取
        skip: 跳过的记录数，默认为 0
        limit: 返回的最大记录数，默认为 100
    
    Returns:
        List[ImageRecordOut]: 图片记录列表
    """
    # 查询数据库，按上传时间倒序排序，支持分页
    records = db.query(ImageRecord).order_by(ImageRecord.upload_time.desc()).offset(skip).limit(limit).all()
    # 将 ORM 模型转换为响应模型
    return [ImageRecordOut.model_validate(r) for r in records]


@router.post("/upload", response_model=UploadImagesResponse)
async def upload_images(
    files: List[UploadFile] = File(...),
    split: str = "custom",
    source_dataset: Optional[str] = None,
    db: Session = Depends(get_db),
) -> UploadImagesResponse:
    """上传图片并生成描述
    
    批量上传图片，生成结构化描述，并将描述写入向量库。
    使用 LangChain 框架实现图像处理和描述生成。
    
    Args:
        files: 上传的文件列表
        split: 数据集分割类型，默认为 "custom"
        source_dataset: 图像来源数据集，可为空
        db: 数据库会话，通过依赖注入获取
    
    Returns:
        UploadImagesResponse: 上传结果，包含处理后的图片记录列表
    """
    # 使用 LangChain 适配器处理上传的图片
    adapter = get_langchain_adapter()
    processed = await adapter.process_image_uploads(
        db=db,
        files=files,
        split=split,
        source_dataset=source_dataset,
    )
    # 提取处理后的记录
    records = [rec for rec, _desc in processed]
    # 构建响应
    return UploadImagesResponse(images=[ImageRecordOut.model_validate(r) for r in records])
