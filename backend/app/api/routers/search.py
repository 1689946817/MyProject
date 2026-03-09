"""
搜索 API 路由模块

该模块定义了搜索相关的 API 路由，包括：
- 文本到图像搜索：根据文本查询检索相关图像
- 图像到图像搜索：根据输入图像检索相似图像

所有路由都以 /api/search 为前缀。
"""
from typing import List

from fastapi import APIRouter, File, UploadFile

from app.application.dispatcher import image_to_image_search, text_to_image_search
from app.application.schemas import (
    ImageSearchResponse,
    SearchResultItem,
    TextSearchRequest,
    TextSearchResponse,
)


# 创建 API 路由器，设置前缀和标签
router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("/text-to-image", response_model=TextSearchResponse)
async def text_to_image(body: TextSearchRequest) -> TextSearchResponse:
    """文本到图像搜索
    
    根据文本查询检索相关图像。
    
    Args:
        body: 搜索请求参数，包含查询文本和返回结果数量
    
    Returns:
        TextSearchResponse: 搜索结果，包含查询文本和相关图像列表
    """
    # 调用文本到图像搜索服务
    hits = await text_to_image_search(query=body.query, top_k=body.top_k)
    # 处理搜索结果
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
    # 构建响应
    return TextSearchResponse(query=body.query, results=results)


@router.post("/image-to-image", response_model=ImageSearchResponse)
async def image_to_image(
    file: UploadFile = File(...),
    top_k: int = 10,
) -> ImageSearchResponse:
    """图像到图像搜索
    
    根据输入图像检索相似图像。
    
    Args:
        file: 上传的图像文件
        top_k: 返回的结果数量，默认为 10
    
    Returns:
        ImageSearchResponse: 搜索结果，包含生成的查询描述和相似图像列表
    """
    # 调用图像到图像搜索服务
    hits, query_desc = await image_to_image_search(file=file, top_k=top_k)
    # 处理搜索结果
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
    # 构建响应
    return ImageSearchResponse(query_description=query_desc, results=results)

