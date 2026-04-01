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

from pydantic import BaseModel, Field


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


class ChatSourceItem(BaseModel):
    """聊天来源快照项。"""

    source_type: str
    source_id: str
    title: Optional[str] = None
    file_path: Optional[str] = None
    content: Optional[str] = None
    score: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """聊天响应模型

    用于返回 RAG 聊天的结果，包括生成的回答和检索到的图像。
    """
    answer: str  # 生成的回答
    results: List[SearchResultItem] = Field(default_factory=list)  # 检索到的相关图像列表
    sources: List[ChatSourceItem] = Field(default_factory=list)
    session_id: Optional[str] = None  # 会话 ID（多轮对话）


class ChatSessionCreateResponse(BaseModel):
    """创建聊天会话响应。"""

    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    """聊天消息输出模型。"""

    id: int
    session_id: str
    role: str
    content: str
    has_image: bool = False
    sources: List[ChatSourceItem] = Field(default_factory=list)
    retrieval_params: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionDetailResponse(BaseModel):
    """聊天会话详情响应。"""

    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessageOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChatSessionRenameRequest(BaseModel):
    """聊天会话重命名请求。"""

    title: str


class DeleteResponse(BaseModel):
    """删除结果响应。"""

    success: bool


class DocumentRecordOut(BaseModel):
    """文档记录输出模型"""
    id: str
    file_name: str
    file_path: str
    upload_time: datetime
    status: str
    chunk_count: int = 0
    image_count: int = 0

    model_config = {"from_attributes": True}


class UploadDocumentResponse(BaseModel):
    """上传文档响应模型"""
    document: DocumentRecordOut
    message: str = ""


class DocChunk(BaseModel):
    """文档文本片段"""
    doc_id: str
    chunk_index: int
    content: str
    score: float


class DocParseResult(BaseModel):
    """文档解析结果（文本片段 + 图片记录）"""
    document: DocumentRecordOut
    chunks: List[DocChunk]
    images: List[ImageRecordOut]

