from __future__ import annotations

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
import json
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def _parse_tags(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _parse_json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


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
    title: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    enabled: bool = True
    custom_metadata: dict[str, Any] = Field(default_factory=dict)
    asset_type: Optional[str] = None
    page_number: Optional[int] = None
    table_index_on_page: Optional[int] = None
    table_group_id: Optional[str] = None
    continued_from_previous_page: bool = False
    continued_to_next_page: bool = False
    fallback_reason: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def enrich_from_extra_metadata(cls, value: Any) -> Any:
        if isinstance(value, dict):
            payload = dict(value)
        else:
            payload = {
                "id": getattr(value, "id", None),
                "file_path": getattr(value, "file_path", None),
                "upload_time": getattr(value, "upload_time", None),
                "generated_description": getattr(value, "generated_description", None),
                "status": getattr(value, "status", None),
                "source_dataset": getattr(value, "source_dataset", None),
                "title": getattr(value, "title", None),
                "tags": getattr(value, "tags", None),
                "notes": getattr(value, "notes", None),
                "enabled": getattr(value, "enabled", True),
                "custom_metadata": getattr(value, "custom_metadata", None),
            }
            extra_metadata = getattr(value, "extra_metadata", None)
            payload["extra_metadata"] = extra_metadata

        extra = _parse_json_dict(payload.get("extra_metadata"))
        payload.setdefault("asset_type", extra.get("asset_type"))
        payload.setdefault("page_number", extra.get("page_number"))
        payload.setdefault("table_index_on_page", extra.get("table_index_on_page"))
        payload.setdefault("table_group_id", extra.get("table_group_id"))
        payload.setdefault(
            "continued_from_previous_page",
            bool(extra.get("continued_from_previous_page", False)),
        )
        payload.setdefault(
            "continued_to_next_page",
            bool(extra.get("continued_to_next_page", False)),
        )
        payload.setdefault("fallback_reason", extra.get("fallback_reason"))
        payload.pop("extra_metadata", None)
        return payload

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, value: Any) -> List[str]:
        return _parse_tags(value)

    @field_validator("custom_metadata", mode="before")
    @classmethod
    def validate_custom_metadata(cls, value: Any) -> dict[str, Any]:
        return _parse_json_dict(value)

    # 配置项，允许从 ORM 模型直接转换
    model_config = {"from_attributes": True}


class UploadImagesResponse(BaseModel):
    """上传图像响应模型
    
    用于返回批量上传图像的结果。
    """
    images: List[ImageRecordOut]  # 上传的图像记录列表
    timings: Optional["TimingSummary"] = None


class SearchResultItem(BaseModel):
    """搜索结果项模型
    
    用于表示单个搜索结果，包含图像信息和相似度分数。
    """
    id: str  # 图像唯一标识符
    file_path: Optional[str] = None  # 图像文件路径，可为空
    description: Optional[str] = None  # 图像描述，可为空
    score: float  # 原始检索分数，保留兼容用途
    relevance_score: Optional[float] = None  # 统一相关性分数，值越大越相关
    score_source: Optional[str] = None  # 相关性分数来源：rerank / rrf / vector
    asset_type: Optional[str] = None
    page_number: Optional[int] = None
    table_group_id: Optional[str] = None
    continued_from_previous_page: bool = False
    continued_to_next_page: bool = False


class TextSearchRequest(BaseModel):
    """文本搜索请求模型
    
    用于接收文本搜索的请求参数。
    """
    query: str  # 搜索查询文本
    top_k: Optional[int] = None  # 返回的结果数量，未提供时使用系统默认值
    enable_score_filter: Optional[bool] = None
    min_relevance_score: Optional[float] = None


class TextSearchResponse(BaseModel):
    """文本搜索响应模型
    
    用于返回文本搜索的结果。
    """
    query: str  # 搜索查询文本
    results: List[SearchResultItem]  # 搜索结果列表
    timings: Optional["TimingSummary"] = None


class ImageSearchResponse(BaseModel):
    """图像搜索响应模型

    用于返回图像搜索的结果，包括生成的查询描述。
    """
    query_description: str  # 基于输入图像生成的查询描述
    results: List[SearchResultItem]  # 搜索结果列表
    timings: Optional["TimingSummary"] = None


class TimingStage(BaseModel):
    name: str
    elapsed_ms: float
    status: str = "ok"
    meta: dict[str, Any] = Field(default_factory=dict)


class TimingSummary(BaseModel):
    trace_id: str
    request_path: str
    request_kind: str
    total_ms: float
    first_token_ms: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    stages: List[TimingStage] = Field(default_factory=list)


class ChatSourceItem(BaseModel):
    """聊天来源快照项。"""

    source_type: str
    source_id: str
    title: Optional[str] = None
    file_path: Optional[str] = None
    content: Optional[str] = None
    score: Optional[float] = None
    rerank_score: Optional[float] = None
    relevance_score: Optional[float] = None
    score_source: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatCitationChunkRef(BaseModel):
    """引用命中的文档片段定位信息。"""

    doc_id: str
    chunk_index: int
    page_number: Optional[int] = None


class ChatCitationItem(BaseModel):
    """段落级引用信息。"""

    paragraph_key: str
    paragraph_index: int
    source_ids: List[str] = Field(default_factory=list)
    doc_chunk_refs: List[ChatCitationChunkRef] = Field(default_factory=list)
    confidence: Optional[float] = None


class ChatResponse(BaseModel):
    """聊天响应模型

    用于返回 RAG 聊天的结果，包括生成的回答和检索到的图像。
    """
    answer: str  # 生成的回答
    results: List[SearchResultItem] = Field(default_factory=list)  # 检索到的相关图像列表
    sources: List[ChatSourceItem] = Field(default_factory=list)
    session_id: Optional[str] = None  # 会话 ID（多轮对话）
    presentation_mode: str = "rag_answer"
    execution_mode: str = "multimodal_rag"
    use_rag: bool = True
    has_uploaded_image: bool = False
    retrieval_steps: List[dict[str, Any]] = Field(default_factory=list)
    citations: List[ChatCitationItem] = Field(default_factory=list)
    timings: Optional[TimingSummary] = None


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
    citations: List[ChatCitationItem] = Field(default_factory=list)
    retrieval_params: Optional[dict[str, Any]] = None
    retrieval_steps: List[dict[str, Any]] = Field(default_factory=list)
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
    message: str = ""
    warnings: List[str] = Field(default_factory=list)


class ConfigOption(BaseModel):
    label: str
    value: str


class ConfigGroupOut(BaseModel):
    key: str
    label: str
    description: Optional[str] = None


class ConfigItemOut(BaseModel):
    key: str
    group: str
    label: str
    description: str
    inputType: str
    parseAs: str
    value: Any = None
    sensitive: bool = False
    required: bool = False
    restartRequired: bool = True
    placeholder: Optional[str] = None
    options: List[ConfigOption] = Field(default_factory=list)


class AdminConfigResponse(BaseModel):
    groups: List[ConfigGroupOut]
    items: List[ConfigItemOut]
    restart_required: bool = True
    message: str


class AdminConfigUpdateRequest(BaseModel):
    values: dict[str, Any]


class AdminConfigUpdateResponse(BaseModel):
    success: bool
    message: str
    restart_required: bool = True


class AdminConfigErrorDetail(BaseModel):
    field_errors: dict[str, str] = Field(default_factory=dict)
    message: str


class DocumentRecordOut(BaseModel):
    """文档记录输出模型"""
    id: str
    file_name: str
    title: Optional[str] = None
    file_path: str
    upload_time: datetime
    status: str
    chunk_count: int = 0
    image_count: int = 0
    document_type: str = "pdf"
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    enabled: bool = True
    custom_metadata: dict[str, Any] = Field(default_factory=dict)
    parse_backend: str = "local"
    parse_stage: str = "queued"
    progress_percent: int = 0
    progress_message: Optional[str] = None

    @field_validator("tags", mode="before")
    @classmethod
    def validate_doc_tags(cls, value: Any) -> List[str]:
        return _parse_tags(value)

    @field_validator("custom_metadata", mode="before")
    @classmethod
    def validate_doc_custom_metadata(cls, value: Any) -> dict[str, Any]:
        return _parse_json_dict(value)

    model_config = {"from_attributes": True}


class ImageRecordUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    enabled: Optional[bool] = None
    source_dataset: Optional[str] = Field(default=None, max_length=100)
    custom_metadata: Optional[dict[str, Any]] = None


class DocumentRecordUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    enabled: Optional[bool] = None
    document_type: Optional[str] = Field(default=None, max_length=50)
    custom_metadata: Optional[dict[str, Any]] = None


class UploadDocumentResponse(BaseModel):
    """上传文档响应模型"""
    document: DocumentRecordOut
    message: str = ""
    timings: Optional[TimingSummary] = None


class DocumentProgressResponse(BaseModel):
    """文档上传/解析进度响应模型"""
    document: DocumentRecordOut
    status: str
    stage: str
    progress_percent: int = 0
    message: Optional[str] = None
    timings: Optional[TimingSummary] = None


class DocChunk(BaseModel):
    """文档文本片段"""
    doc_id: str
    chunk_index: int
    content: str
    score: float
    page_number: Optional[int] = None
    source_type: Optional[str] = None


class DocParseResult(BaseModel):
    """文档解析结果（文本片段 + 图片记录）"""
    document: DocumentRecordOut
    chunks: List[DocChunk]
    images: List[ImageRecordOut]
    timings: Optional[TimingSummary] = None
