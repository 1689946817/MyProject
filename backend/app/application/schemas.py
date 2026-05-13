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
    """将 tags 字段统一解析为字符串列表。

    支持输入类型：None（返回空列表）、list（逐项转字符串并去除空白）、
    str（按逗号分隔并去除空白项）。

    参数:
        value: 原始 tags 值，可能为 None / list / str。

    返回:
        去重并去除空白后的标签列表。
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _parse_json_dict(value: Any) -> dict[str, Any]:
    """将 JSON 字符串或 dict 统一解析为 dict。

    支持输入类型：None（返回空 dict）、dict（原样返回）、
    str（尝试 JSON 反序列化，失败则返回空 dict）。

    参数:
        value: 原始值，可能为 None / dict / JSON 字符串。

    返回:
        解析后的字典，解析失败时返回空字典。
    """
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
    title: Optional[str] = None  # 用户自定义标题
    tags: List[str] = Field(default_factory=list)  # 标签列表
    notes: Optional[str] = None  # 用户备注
    enabled: bool = True  # 是否启用（禁用后检索不返回）
    custom_metadata: dict[str, Any] = Field(default_factory=dict)  # 自定义元数据键值对
    asset_type: Optional[str] = None  # 资产类型（如 table / figure / text）
    page_number: Optional[int] = None  # 所在页码（文档解析场景）
    table_index_on_page: Optional[int] = None  # 同一页中表格的序号
    table_group_id: Optional[str] = None  # 跨页表格分组标识
    continued_from_previous_page: bool = False  # 是否从前一页续接
    continued_to_next_page: bool = False  # 是否续接到后一页
    fallback_reason: Optional[str] = None  # 降级处理原因
    parent_doc_id: Optional[str] = None  # 所属文档 ID
    content_hash: Optional[str] = None  # 内容哈希（去重用）
    logical_asset_id: Optional[str] = None  # 逻辑资产 ID（多版本关联）
    version_number: int = 1  # 版本号
    is_latest: bool = True  # 是否为最新版本
    deduplicated: bool = False  # 是否已去重
    duplicate_of: Optional[str] = None  # 去重时指向的原始记录 ID

    @model_validator(mode="before")
    @classmethod
    def enrich_from_extra_metadata(cls, value: Any) -> Any:
        """在模型验证前从 extra_metadata JSON 中提取扩展字段。

        将 extra_metadata 中的 asset_type、page_number、table_index_on_page、
        table_group_id、continued_from_previous_page、continued_to_next_page、
        fallback_reason 等字段提升到顶层，供 Pydantic 直接映射。
        """
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
                "parent_doc_id": getattr(value, "parent_doc_id", None),
                "content_hash": getattr(value, "content_hash", None),
                "logical_asset_id": getattr(value, "logical_asset_id", None),
                "version_number": getattr(value, "version_number", 1),
                "is_latest": getattr(value, "is_latest", True),
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
        """tags 字段预处理：统一转为字符串列表。"""
        return _parse_tags(value)

    @field_validator("custom_metadata", mode="before")
    @classmethod
    def validate_custom_metadata(cls, value: Any) -> dict[str, Any]:
        """custom_metadata 字段预处理：统一解析为字典。"""
        return _parse_json_dict(value)

    # 配置项，允许从 ORM 模型直接转换
    model_config = {"from_attributes": True}


class UploadImagesResponse(BaseModel):
    """上传图像响应模型
    
    用于返回批量上传图像的结果。
    """
    images: List[ImageRecordOut]  # 上传的图像记录列表
    deduplicated_count: int = 0
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
    """单个计时阶段的耗时记录。"""

    name: str  # 阶段名称（如 retrieval、llm_generation）
    elapsed_ms: float  # 耗时（毫秒）
    status: str = "ok"  # 阶段状态：ok / error / skipped
    meta: dict[str, Any] = Field(default_factory=dict)  # 附加元信息


class TimingSummary(BaseModel):
    """请求级计时汇总，用于前端性能展示与后端审计。"""

    trace_id: str  # 请求追踪 ID
    request_path: str  # 请求路径（如 /api/rag/chat）
    request_kind: str  # 请求类型（如 rag_chat、text_search）
    total_ms: float  # 总耗时（毫秒）
    first_token_ms: Optional[float] = None  # 流式场景首 token 延迟（毫秒）
    metadata: dict[str, Any] = Field(default_factory=dict)  # 请求级元信息
    stages: List[TimingStage] = Field(default_factory=list)  # 各阶段耗时明细


class ChatSourceItem(BaseModel):
    """聊天来源快照项。

    记录 RAG 检索命中的单个来源，用于前端展示和引用构建。
    """

    source_type: str  # 来源类型：image / document_chunk
    source_id: str  # 来源唯一标识符
    title: Optional[str] = None  # 来源标题
    file_path: Optional[str] = None  # 文件路径
    content: Optional[str] = None  # 文本内容摘要
    score: Optional[float] = None  # 向量检索原始分数
    rerank_score: Optional[float] = None  # 重排模型分数
    relevance_score: Optional[float] = None  # 统一相关性分数
    score_source: Optional[str] = None  # 分数来源：rerank / rrf / vector
    metadata: dict[str, Any] = Field(default_factory=dict)  # 附加元信息


class ChatCitationChunkRef(BaseModel):
    """引用命中的文档片段定位信息。

    用于精确指向某文档中的特定 chunk 及其页码。
    """

    doc_id: str  # 文档 ID
    chunk_index: int  # 片段在文档中的序号
    page_number: Optional[int] = None  # 所在页码


class ChatCitationItem(BaseModel):
    """段落级引用信息。

    将回答中的每个段落映射到高置信度的来源列表。
    """

    paragraph_key: str  # 段落键名（如 p-0）
    paragraph_index: int  # 段落序号
    source_ids: List[str] = Field(default_factory=list)  # 命中的来源 ID 列表
    doc_chunk_refs: List[ChatCitationChunkRef] = Field(default_factory=list)  # 文档片段定位
    confidence: Optional[float] = None  # 最高匹配置信度


class ChatResponse(BaseModel):
    """聊天响应模型

    用于返回 RAG 聊天的结果，包括生成的回答和检索到的图像。
    """
    answer: str  # 生成的回答
    results: List[SearchResultItem] = Field(default_factory=list)  # 检索到的相关图像列表
    sources: List[ChatSourceItem] = Field(default_factory=list)
    session_id: Optional[str] = None  # 会话 ID（多轮对话）
    chat_mode: str = "default"
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
    feedback: Optional["AnswerFeedbackOut"] = None
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
    """配置项下拉选项。"""

    label: str  # 显示名称
    value: str  # 选项值


class ConfigGroupOut(BaseModel):
    """配置分组输出。"""

    key: str  # 分组唯一键
    label: str  # 分组显示名称
    description: Optional[str] = None  # 分组描述


class ConfigItemOut(BaseModel):
    """单个配置项输出，供前端表单渲染。"""

    key: str  # 配置键名
    group: str  # 所属分组键
    label: str  # 显示名称
    description: str  # 配置说明
    inputType: str  # 输入控件类型（text / number / toggle / select）
    parseAs: str  # 值解析方式（string / int / float / bool / json）
    value: Any = None  # 当前值
    sensitive: bool = False  # 是否敏感（前端脱敏展示）
    required: bool = False  # 是否必填
    restartRequired: bool = True  # 修改后是否需要重启
    placeholder: Optional[str] = None  # 占位提示文本
    options: List[ConfigOption] = Field(default_factory=list)  # 下拉选项列表


class AdminConfigResponse(BaseModel):
    """管理后台配置查询响应。"""

    groups: List[ConfigGroupOut]  # 配置分组列表
    items: List[ConfigItemOut]  # 配置项列表
    restart_required: bool = True  # 是否需要重启
    message: str  # 提示信息


class AdminConfigUpdateRequest(BaseModel):
    """管理后台配置更新请求。"""

    values: dict[str, Any]  # 待更新的键值对


class AdminConfigUpdateResponse(BaseModel):
    """管理后台配置更新响应。"""

    success: bool  # 是否成功
    message: str  # 结果信息
    restart_required: bool = True  # 是否需要重启生效


class AdminConfigErrorDetail(BaseModel):
    """配置验证错误详情。"""

    field_errors: dict[str, str] = Field(default_factory=dict)  # 字段级错误信息
    message: str  # 整体错误描述


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
    content_hash: Optional[str] = None
    logical_asset_id: Optional[str] = None
    version_number: int = 1
    is_latest: bool = True
    deduplicated: bool = False
    duplicate_of: Optional[str] = None

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
    """图像记录更新请求。所有字段可选，仅更新传入的字段。"""

    title: Optional[str] = Field(default=None, max_length=200)  # 标题（最多 200 字符）
    tags: Optional[List[str]] = None  # 标签列表
    notes: Optional[str] = Field(default=None, max_length=2000)  # 备注（最多 2000 字符）
    enabled: Optional[bool] = None  # 是否启用
    source_dataset: Optional[str] = Field(default=None, max_length=100)  # 来源数据集
    custom_metadata: Optional[dict[str, Any]] = None  # 自定义元数据


class DocumentRecordUpdateRequest(BaseModel):
    """文档记录更新请求。所有字段可选，仅更新传入的字段。"""

    title: Optional[str] = Field(default=None, max_length=200)  # 标题（最多 200 字符）
    tags: Optional[List[str]] = None  # 标签列表
    notes: Optional[str] = Field(default=None, max_length=2000)  # 备注（最多 2000 字符）
    enabled: Optional[bool] = None  # 是否启用
    document_type: Optional[str] = Field(default=None, max_length=50)  # 文档类型
    custom_metadata: Optional[dict[str, Any]] = None  # 自定义元数据


class UploadDocumentResponse(BaseModel):
    """上传文档响应模型"""
    document: DocumentRecordOut
    job: Optional["JobTaskOut"] = None
    message: str = ""
    timings: Optional[TimingSummary] = None


class DocumentProgressResponse(BaseModel):
    """文档上传/解析进度响应模型"""
    document: DocumentRecordOut
    status: str
    stage: str
    progress_percent: int = 0
    message: Optional[str] = None
    job: Optional["JobTaskOut"] = None
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


class JobTaskOut(BaseModel):
    """异步任务输出模型。"""

    id: str  # 任务唯一标识符
    job_type: str  # 任务类型：document_parse / document_reprocess / batch_import
    status: str  # 任务状态：pending / running / completed / failed / cancelled
    priority: int = 100  # 优先级（数值越小优先级越高）
    payload: dict[str, Any] = Field(default_factory=dict)  # 任务入参
    result: dict[str, Any] = Field(default_factory=dict)  # 任务结果
    error_message: Optional[str] = None  # 错误信息
    retry_count: int = 0  # 已重试次数
    max_retries: int = 0  # 最大重试次数
    locked_by: Optional[str] = None  # 锁定任务的 worker ID
    related_doc_id: Optional[str] = None  # 关联文档 ID
    related_batch_id: Optional[str] = None  # 关联批次 ID
    created_at: datetime  # 创建时间
    started_at: Optional[datetime] = None  # 开始执行时间
    finished_at: Optional[datetime] = None  # 完成时间

    @model_validator(mode="before")
    @classmethod
    def normalize_job_payloads(cls, value: Any) -> Any:
        """在模型验证前将 ORM 字段（payload_json / result_json）转为顶层字段。"""
        if isinstance(value, dict):
            payload = dict(value)
        else:
            payload = {
                "id": getattr(value, "id", None),
                "job_type": getattr(value, "job_type", None),
                "status": getattr(value, "status", None),
                "priority": getattr(value, "priority", 100),
                "payload": getattr(value, "payload_json", None),
                "result": getattr(value, "result_json", None),
                "error_message": getattr(value, "error_message", None),
                "retry_count": getattr(value, "retry_count", 0),
                "max_retries": getattr(value, "max_retries", 0),
                "locked_by": getattr(value, "locked_by", None),
                "related_doc_id": getattr(value, "related_doc_id", None),
                "related_batch_id": getattr(value, "related_batch_id", None),
                "created_at": getattr(value, "created_at", None),
                "started_at": getattr(value, "started_at", None),
                "finished_at": getattr(value, "finished_at", None),
            }
        payload["payload"] = _parse_json_dict(payload.get("payload"))
        payload["result"] = _parse_json_dict(payload.get("result"))
        return payload

    model_config = {"from_attributes": True}


class ImportBatchOut(BaseModel):
    """批量导入批次输出模型。"""

    id: str  # 批次唯一标识符
    source_type: str  # 来源类型（如 document）
    status: str  # 批次状态：pending / running / completed / failed
    summary: dict[str, Any] = Field(default_factory=dict)  # 汇总统计（各状态任务数）
    created_at: datetime  # 创建时间
    updated_at: datetime  # 最后更新时间

    @model_validator(mode="before")
    @classmethod
    def normalize_import_batch(cls, value: Any) -> Any:
        """在模型验证前将 ORM 字段 summary_json 转为顶层 summary 字段。"""
        if isinstance(value, dict):
            payload = dict(value)
        else:
            payload = {
                "id": getattr(value, "id", None),
                "source_type": getattr(value, "source_type", None),
                "status": getattr(value, "status", None),
                "summary": getattr(value, "summary_json", None),
                "created_at": getattr(value, "created_at", None),
                "updated_at": getattr(value, "updated_at", None),
            }
        payload["summary"] = _parse_json_dict(payload.get("summary"))
        return payload

    model_config = {"from_attributes": True}


class BatchImportResponse(BaseModel):
    """批量导入响应。"""

    batch: ImportBatchOut  # 批次信息
    jobs: List[JobTaskOut] = Field(default_factory=list)  # 创建的任务列表
    documents: List[DocumentRecordOut] = Field(default_factory=list)  # 创建的文档列表
    message: str = ""  # 提示信息
    timings: Optional[TimingSummary] = None  # 计时信息


class AnswerFeedbackRequest(BaseModel):
    """用户对回答的反馈请求。"""

    rating: str = Field(pattern="^(up|down)$")  # 评价：up（有用）/ down（无用）
    issue_types: List[str] = Field(default_factory=list)  # 问题类型标签列表
    comment: Optional[str] = Field(default=None, max_length=2000)  # 用户评论（最多 2000 字符）


class AnswerFeedbackOut(BaseModel):
    """用户反馈输出模型。"""

    id: int  # 反馈记录 ID
    session_id: Optional[str] = None  # 会话 ID
    assistant_message_id: int  # 被评价的助手消息 ID
    rating: str  # 评价：up / down
    issue_types: List[str] = Field(default_factory=list)  # 问题类型标签
    comment: Optional[str] = None  # 用户评论
    query: Optional[str] = None  # 原始用户提问
    retrieval_snapshot: dict[str, Any] = Field(default_factory=dict)  # 检索快照（调试用）
    created_at: datetime  # 创建时间

    @model_validator(mode="before")
    @classmethod
    def normalize_feedback(cls, value: Any) -> Any:
        """在模型验证前将 ORM 字段（issue_types_json / retrieval_snapshot_json）转为顶层字段。"""
        if isinstance(value, dict):
            payload = dict(value)
        else:
            payload = {
                "id": getattr(value, "id", None),
                "session_id": getattr(value, "session_id", None),
                "assistant_message_id": getattr(value, "assistant_message_id", None),
                "rating": getattr(value, "rating", None),
                "issue_types": getattr(value, "issue_types_json", None),
                "comment": getattr(value, "comment", None),
                "query": getattr(value, "query", None),
                "retrieval_snapshot": getattr(value, "retrieval_snapshot_json", None),
                "created_at": getattr(value, "created_at", None),
            }
        raw_issue_types = payload.get("issue_types")
        if isinstance(raw_issue_types, str):
            try:
                loaded = json.loads(raw_issue_types)
            except (TypeError, ValueError, json.JSONDecodeError):
                loaded = []
            payload["issue_types"] = loaded if isinstance(loaded, list) else []
        elif not isinstance(raw_issue_types, list):
            payload["issue_types"] = []
        payload["retrieval_snapshot"] = _parse_json_dict(payload.get("retrieval_snapshot"))
        return payload

    model_config = {"from_attributes": True}


class HealthStatusResponse(BaseModel):
    """健康检查响应。"""

    status: str  # 整体状态：healthy / degraded / unhealthy
    checks: dict[str, Any] = Field(default_factory=dict)  # 各子项检查结果
    generated_at: datetime  # 检查时间
