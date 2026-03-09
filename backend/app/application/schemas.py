"""
数据模型定义模块

该模块定义了 API 接口的请求和响应数据模型，使用 Pydantic V2 语法，包括：
- 图像记录输出模型
- 上传图像响应模型
- 搜索结果项模型
- 文本搜索请求和响应模型
- 图像搜索响应模型
- 聊天响应模型

这些模型用于 API 接口的参数验证和响应格式化。
"""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class ImageRecordOut(BaseModel):
    """图像记录输出模型
    
    用于返回图像记录的详细信息，包括元数据和生成的描述。
    """
    id: str  # 图像唯一标识符
    file_path: str  # 图像文件路径
    upload_time: datetime  # 上传时间
    generated_description: Optional[str] = None  # 生成的图像描述，可为空
    status: str  # 处理状态（Processing、Completed、Failed）
    source_dataset: Optional[str] = None  # 图像来源数据集，可为空

    # 配置项，允许从 ORM 模型直接转换
    model_config = {"from_attributes": True}


class UploadImagesResponse(BaseModel):
    """上传图像响应模型
    
    用于返回批量上传图像的结果。
    """
    images: List[ImageRecordOut]  # 上传的图像记录列表


class SearchResultItem(BaseModel):
    """搜索结果项模型
    
    用于表示单个搜索结果，包含图像信息和相似度分数。
    """
    id: str  # 图像唯一标识符
    file_path: Optional[str] = None  # 图像文件路径，可为空
    description: Optional[str] = None  # 图像描述，可为空
    score: float  # 相似度分数，值越小相似度越高


class TextSearchRequest(BaseModel):
    """文本搜索请求模型
    
    用于接收文本搜索的请求参数。
    """
    query: str  # 搜索查询文本
    top_k: int = 10  # 返回的结果数量，默认为 10


class TextSearchResponse(BaseModel):
    """文本搜索响应模型
    
    用于返回文本搜索的结果。
    """
    query: str  # 搜索查询文本
    results: List[SearchResultItem]  # 搜索结果列表


class ImageSearchResponse(BaseModel):
    """图像搜索响应模型
    
    用于返回图像搜索的结果，包括生成的查询描述。
    """
    query_description: str  # 基于输入图像生成的查询描述
    results: List[SearchResultItem]  # 搜索结果列表


class ChatResponse(BaseModel):
    """聊天响应模型
    
    用于返回 RAG 聊天的结果，包括生成的回答和检索到的图像。
    """
    answer: str  # 生成的回答
    results: List[SearchResultItem]  # 检索到的相关图像列表

