"""
管理端配置服务模块。

本模块负责后台管理界面的配置项管理，提供以下核心功能：
- 定义所有可管理配置项的元数据（字段类型、分组、校验规则等）
- 从 .env 文件读取配置值并序列化为前端可用的结构
- 接收前端提交的配置更新，校验后写回 .env 文件
- 支持多种数据类型解析：字符串、布尔值、整数、浮点数、CSV、URL、路径

配置项按分组组织（基础信息、基础设施、文档解析、模型服务、RAG 功能、检索与排序、评测），
管理端前端据此渲染分组表单。
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from app.core.config import _BACKEND_DIR

# 配置值的解析类型，决定如何将字符串值转换为 Python 类型
ParseAs = Literal["string", "bool", "int", "float", "csv", "url", "path"]
# 前端表单控件类型，决定管理界面渲染何种输入组件
InputType = Literal["text", "textarea", "password", "switch", "number", "select"]


class ConfigValidationError(Exception):
    """配置校验异常。

    当前端提交的配置值存在一个或多个字段校验错误时抛出。
    属性 field_errors 记录每个出错字段的错误描述。
    """

    def __init__(self, field_errors: dict[str, str], message: str = "配置校验失败") -> None:
        super().__init__(message)
        # 字段名 → 错误描述的映射
        self.field_errors = field_errors
        self.message = message


@dataclass(frozen=True)
class ConfigFieldMeta:
    """配置字段元数据。

    描述单个可管理配置项的全部属性，用于前端表单渲染和后端值解析。
    使用 frozen=True 保证实例不可变，防止运行时被意外修改。
    """

    key: str                                         # .env 中的变量名，如 "MLLM_BASE_URL"
    group: str                                       # 所属分组 key，对应 CONFIG_GROUPS
    label: str                                       # 前端展示名称
    description: str                                 # 前端展示的说明文字
    parse_as: ParseAs = "string"                     # 值解析类型
    input_type: InputType = "text"                   # 前端控件类型
    sensitive: bool = False                          # 是否为敏感信息（密钥等），前端做脱敏展示
    required: bool = False                           # 是否必填
    restart_required: bool = True                    # 修改后是否需要重启后端
    placeholder: Optional[str] = None                # 输入框占位提示
    options: Optional[list[dict[str, str]]] = None   # select 控件的选项列表
    default: Any = None                              # 默认值


# 配置分组定义，前端据此渲染分组 Tab 或折叠面板
CONFIG_GROUPS: list[dict[str, str]] = [
    {"key": "basic", "label": "基础信息", "description": "系统名称与对外展示相关配置。"},
    {"key": "infra", "label": "基础设施", "description": "存储、数据库、路径与代理相关基础配置。"},
    {"key": "doc_parse", "label": "文档解析", "description": "文档解析后端与 MinerU 相关配置。"},
    {"key": "models", "label": "模型服务", "description": "多模态、向量与文本生成模型服务地址和密钥。"},
    {"key": "rag", "label": "RAG 功能", "description": "问答流程、对话记忆和 Agentic RAG 开关。"},
    {"key": "retrieval", "label": "检索与排序", "description": "检索候选、重排和混合检索参数。"},
    {"key": "eval", "label": "评测", "description": "评测模型与服务配置。"},
]


def _select_options(values: list[str]) -> list[dict[str, str]]:
    """将字符串列表转换为前端 select 控件的 options 格式。"""
    return [{"label": value, "value": value} for value in values]


# 全部可管理配置项的元数据列表
# 每一项对应 .env 中的一个环境变量，管理端前端据此渲染表单
CONFIG_FIELDS: list[ConfigFieldMeta] = [
    ConfigFieldMeta("APP_NAME", "basic", "系统名称", "网页与后端服务使用的系统显示名称。", default="Multimodal RAG Base"),
    ConfigFieldMeta(
        "BACKEND_CORS_ORIGINS",
        "infra",
        "允许跨域来源",
        "允许访问后端接口的前端地址，多个地址用英文逗号分隔。",
        parse_as="csv",
        input_type="textarea",
        placeholder="http://localhost:5173,http://127.0.0.1:5173",
        default="http://localhost:5173,http://localhost:5174,http://localhost:5175,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175",
    ),
    ConfigFieldMeta("SQLALCHEMY_DATABASE_URI", "infra", "数据库连接串", "后端元数据数据库连接地址。", parse_as="path", default="sqlite:///./app.db"),
    ConfigFieldMeta("CHROMA_PERSIST_DIR", "infra", "向量库存储目录", "Chroma 向量库本地持久化目录。", parse_as="path", default=os.path.join(_BACKEND_DIR, "chroma_data")),
    ConfigFieldMeta("MAIN_IMAGE_COLLECTION_NAME", "infra", "主图片集合名", "主系统图片知识库在 Chroma 中的集合名称。", default="images_main_kb"),
    ConfigFieldMeta("COCO_PROPOSED_COLLECTION_NAME", "infra", "COCO 集合名", "COCO proposed baseline 专用集合名称。", default="images_coco_proposed"),
    ConfigFieldMeta("DOC_COLLECTION_NAME", "infra", "文档集合名", "文档文本片段向量集合名称。", default="documents_text"),
    ConfigFieldMeta("CHROMA_COLLECTION_NAME", "infra", "历史集合名", "兼容旧版本的历史字段，通常保持空值。"),
    ConfigFieldMeta(
        "PDF_TEXT_LOADER_BACKEND",
        "doc_parse",
        "PDF 文本解析器",
        "PDF 文本抽取时使用的后端解析器。",
        input_type="select",
        options=_select_options(["pymupdf", "pypdf"]),
        default="pymupdf",
    ),
    ConfigFieldMeta("DISABLE_OUTBOUND_PROXY", "infra", "禁用系统代理", "启用后会忽略当前进程继承的 HTTP/HTTPS 代理环境变量。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta(
        "DOC_PARSE_BACKEND",
        "doc_parse",
        "文档解析后端",
        "选择文档解析使用本地流程还是 MinerU 服务。",
        input_type="select",
        options=_select_options(["local", "mineru"]),
        default="local",
    ),
    ConfigFieldMeta("MINERU_API_BASE_URL", "doc_parse", "MinerU 服务地址", "MinerU 远程解析服务的基础 URL。", parse_as="url", default="https://mineru.net"),
    ConfigFieldMeta("MINERU_API_TOKEN", "doc_parse", "MinerU Token", "MinerU 服务鉴权令牌。", sensitive=True, input_type="password"),
    ConfigFieldMeta(
        "MINERU_MODEL_VERSION",
        "doc_parse",
        "MinerU 模型版本",
        "MinerU 使用的模型版本标识。",
        input_type="select",
        options=_select_options(["vlm"]),
        default="vlm",
    ),
    ConfigFieldMeta("MINERU_POLL_INTERVAL_SECONDS", "doc_parse", "MinerU 轮询间隔", "轮询 MinerU 任务状态的时间间隔，单位秒。", parse_as="float", input_type="number", default=2.0),
    ConfigFieldMeta("MINERU_TIMEOUT_SECONDS", "doc_parse", "MinerU 超时时间", "MinerU 请求的最长等待时间，单位秒。", parse_as="int", input_type="number", default=120),
    ConfigFieldMeta("MLLM_BASE_URL", "models", "多模态模型地址", "多模态模型 API 的基础 URL。", parse_as="url"),
    ConfigFieldMeta("MLLM_API_KEY", "models", "多模态模型密钥", "多模态模型服务访问密钥。", sensitive=True, input_type="password"),
    ConfigFieldMeta("MLLM_MODEL_NAME", "models", "多模态模型名", "图文理解或视觉问答所用模型名称。"),
    ConfigFieldMeta("CHAT_COMPLETION_TIMEOUT_SECONDS", "models", "聊天请求超时时间", "聊天模型非流式请求的最长等待时间，单位秒。", parse_as="int", input_type="number", default=180),
    ConfigFieldMeta("ENABLE_TIMING_LOGS", "rag", "启用耗时日志", "开启后在后端日志中记录各请求的分阶段耗时。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("EXPOSE_TIMINGS_IN_API", "rag", "接口返回耗时", "开启后在聊天、检索和上传接口响应中附加结构化耗时数据。", parse_as="bool", input_type="switch", default=False),
    ConfigFieldMeta("EMBEDDING_BASE_URL", "models", "向量模型地址", "文本向量模型 API 的基础 URL。", parse_as="url"),
    ConfigFieldMeta("EMBEDDING_API_KEY", "models", "向量模型密钥", "文本向量模型服务访问密钥。", sensitive=True, input_type="password"),
    ConfigFieldMeta("EMBEDDING_MODEL_NAME", "models", "向量模型名", "文本检索使用的 embedding 模型名称。"),
    ConfigFieldMeta("PADDLEOCR_PYTHON", "doc_parse", "PaddleOCR Python 路径", "OCR 子进程所使用的 Python 解释器路径。", parse_as="path"),
    ConfigFieldMeta("MULTIMODAL_EMBEDDING_API_KEY", "models", "多模态向量密钥", "图文同空间向量模型服务访问密钥。", sensitive=True, input_type="password"),
    ConfigFieldMeta("MULTIMODAL_EMBEDDING_MODEL_NAME", "models", "多模态向量模型名", "图文同空间向量模型名称。"),
    ConfigFieldMeta("LLM_BASE_URL", "models", "大语言模型地址", "RAG 生成回答所使用文本生成模型 API 地址。", parse_as="url"),
    ConfigFieldMeta("LLM_API_KEY", "models", "大语言模型密钥", "文本生成模型服务访问密钥。", sensitive=True, input_type="password"),
    ConfigFieldMeta("LLM_MODEL_NAME", "models", "大语言模型名", "RAG 回答生成使用的模型名称。"),
    ConfigFieldMeta("TASK_LLM_BASE_URL", "models", "轻量任务模型地址", "分类、查询改写、上下文压缩等轻量文本任务所使用模型 API 地址；留空则回退到大语言模型地址。", parse_as="url"),
    ConfigFieldMeta("TASK_LLM_API_KEY", "models", "轻量任务模型密钥", "轻量文本任务模型服务访问密钥；留空则回退到大语言模型密钥。", sensitive=True, input_type="password"),
    ConfigFieldMeta("TASK_LLM_MODEL_NAME", "models", "轻量任务模型名", "分类、查询改写、上下文压缩等轻量文本任务使用的模型名称；留空则回退到大语言模型名。"),
    ConfigFieldMeta("QUERY_REWRITE_ENABLED", "rag", "启用查询改写", "开启后会在检索前对用户问题进行查询改写。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("QUERY_MULTI_QUERY_COUNT", "rag", "查询改写条数", "查询改写生成的候选查询数量。", parse_as="int", input_type="number", default=3),
    ConfigFieldMeta("RERANK_MODEL_NAME", "retrieval", "重排模型名", "文档或图像候选重排序使用的模型名称。", default="BAAI/bge-reranker-base"),
    ConfigFieldMeta("RERANK_MODEL_PATH", "retrieval", "重排模型本地路径", "若配置本地路径，则优先使用本地重排模型。", parse_as="path"),
    ConfigFieldMeta("RERANK_TOP_K", "retrieval", "重排保留数", "重排后最终保留的结果数量。", parse_as="int", input_type="number", default=5),
    ConfigFieldMeta("RERANK_CANDIDATE_K", "retrieval", "重排候选数", "进入重排阶段的候选结果数量。", parse_as="int", input_type="number", default=20),
    ConfigFieldMeta("IMAGE_FAST_RETRIEVAL_ENABLED", "retrieval", "启用快速图像检索", "开启后使用快速候选召回流程提升图像检索速度。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("IMAGE_FAST_RETRIEVAL_CANDIDATE_K", "retrieval", "快速检索候选数", "快速图像检索阶段的候选数量。", parse_as="int", input_type="number", default=8),
    ConfigFieldMeta("IMAGE_GROUNDED_TEXT_AUGMENT_ENABLED", "retrieval", "启用图像引导文本增强", "开启后用图像上下文增强文本检索。", parse_as="bool", input_type="switch", default=False),
    ConfigFieldMeta("IMAGE_GROUNDED_TEXT_TOP_K", "retrieval", "图像引导文本 TopK", "用于图像引导文本增强的候选数量。", parse_as="int", input_type="number", default=2),
    ConfigFieldMeta("IMAGE_GROUNDED_MAX_IMAGES", "retrieval", "图像上下文最大图片数", "单次回答最多使用多少张图像作为上下文。", parse_as="int", input_type="number", default=2),
    ConfigFieldMeta("IMAGE_GROUNDED_MAX_HISTORY_TURNS", "retrieval", "图像上下文最大历史轮数", "图像引导流程可参考的历史对话轮数。", parse_as="int", input_type="number", default=2),
    ConfigFieldMeta("SEARCH_DEFAULT_TOP_K", "retrieval", "搜索默认返回数", "搜索页默认请求的图片返回数量。", parse_as="int", input_type="number", default=10),
    ConfigFieldMeta("SEARCH_ENABLE_SCORE_FILTER", "retrieval", "搜索启用重排序阈值", "开启后搜索页按重排序分数过滤结果；没有重排序分数的结果会跳过过滤。", parse_as="bool", input_type="switch", default=False),
    ConfigFieldMeta("SEARCH_MIN_RELEVANCE_SCORE", "retrieval", "搜索最小重排序分数", "搜索页启用阈值过滤时要求的最小重排序分数。", parse_as="float", input_type="number", default=0.0),
    ConfigFieldMeta("CHAT_DEFAULT_TOP_K", "retrieval", "问答默认返回数", "聊天问答默认检索的来源图片数量。", parse_as="int", input_type="number", default=5),
    ConfigFieldMeta("CHAT_FAST_DEFAULT_TOP_K", "retrieval", "快速模式默认返回数", "聊天快速模式默认检索的来源数量。", parse_as="int", input_type="number", default=2),
    ConfigFieldMeta("CHAT_FAST_DISABLE_QUERY_REWRITE", "rag", "快速模式禁用查询改写", "开启后快速模式跳过查询改写和 Multi-Query 扩展。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("CHAT_FAST_DISABLE_RERANK", "retrieval", "快速模式禁用重排", "开启后快速模式跳过 CrossEncoder 重排，直接截断召回结果。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("CHAT_FAST_DISABLE_CONTEXT_COMPRESSION", "rag", "快速模式禁用上下文压缩", "开启后快速模式跳过上下文压缩阶段。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("CHAT_FAST_FORCE_TRUE_STREAMING", "rag", "快速模式优先真流式", "开启后快速模式优先走真流式首字输出，无法真流式时才回退到回放分块。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("CHAT_EXPERT_DEFAULT_TOP_K", "retrieval", "专家模式默认返回数", "聊天专家模式默认检索的来源数量。", parse_as="int", input_type="number", default=8),
    ConfigFieldMeta("CHAT_EXPERT_RERANK_CANDIDATE_K", "retrieval", "专家模式重排候选数", "专家模式进入重排阶段的候选结果数量。", parse_as="int", input_type="number", default=40),
    ConfigFieldMeta("CHAT_EXPERT_QUERY_MULTI_COUNT", "rag", "专家模式查询扩展条数", "专家模式查询改写生成的候选查询数量。", parse_as="int", input_type="number", default=5),
    ConfigFieldMeta("CHAT_EXPERT_FORCE_QUERY_REWRITE", "rag", "专家模式强制查询改写", "开启后专家模式无视全局设置，始终执行查询改写。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("CHAT_EXPERT_FORCE_RERANK", "retrieval", "专家模式强制重排", "开启后专家模式无视全局设置，始终执行候选重排。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("CHAT_EXPERT_FORCE_CONTEXT_COMPRESSION", "rag", "专家模式强制上下文压缩", "开启后专家模式在复杂检索回答中始终执行上下文压缩。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("CHAT_EXPERT_FORCE_TRUE_STREAMING", "rag", "专家模式优先真流式", "开启后专家模式复杂回答优先走真流式输出。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("CHAT_ENABLE_SCORE_FILTER", "retrieval", "问答启用重排序阈值", "开启后聊天问答仅保留重排序分数超过阈值的来源结果；没有重排序分数的结果会跳过过滤。", parse_as="bool", input_type="switch", default=False),
    ConfigFieldMeta("CHAT_MIN_RELEVANCE_SCORE", "retrieval", "问答最小重排序分数", "聊天问答启用阈值过滤时要求的最小重排序分数。", parse_as="float", input_type="number", default=0.0),
    ConfigFieldMeta("BM25_INDEX_PATH", "retrieval", "BM25 索引路径", "混合检索使用的 BM25 索引文件路径。", parse_as="path", default="storage/bm25_index.pkl"),
    ConfigFieldMeta("HYBRID_VECTOR_WEIGHT", "retrieval", "向量检索权重", "混合检索中向量得分的权重比例。", parse_as="float", input_type="number", default=0.6),
    ConfigFieldMeta("HYBRID_BM25_WEIGHT", "retrieval", "BM25 权重", "混合检索中 BM25 得分的权重比例。", parse_as="float", input_type="number", default=0.4),
    ConfigFieldMeta("CONTEXT_COMPRESSION_ENABLED", "rag", "启用上下文压缩", "开启后会对召回上下文进行压缩以减少提示长度。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("CHAT_HISTORY_MAX_TURNS", "rag", "对话记忆轮数", "RAG 问答可参考的历史对话最大轮数。", parse_as="int", input_type="number", default=5),
    ConfigFieldMeta("AGENTIC_RAG_ENABLED", "rag", "启用 Agentic RAG", "开启后启用 Agentic RAG 流程。", parse_as="bool", input_type="switch", default=False),
    ConfigFieldMeta("CHAT_EXPERT_FORCE_AGENTIC_RAG", "rag", "专家模式强制 Agentic RAG", "开启后专家模式在 RAG 型问题上始终走 Agentic RAG 路线。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("EVAL_BASE_URL", "eval", "评测模型地址", "评测器调用的 OpenAI 兼容服务地址。", parse_as="url"),
    ConfigFieldMeta("EVAL_API_KEY", "eval", "评测模型密钥", "评测器服务访问密钥。", sensitive=True, input_type="password"),
    ConfigFieldMeta("EVAL_MODEL", "eval", "评测模型名", "离线评测使用的模型名称。"),
]

# 按 key 建立快速索引，用于校验前端提交的字段名是否合法
CONFIG_FIELD_MAP = {field.key: field for field in CONFIG_FIELDS}


class ConfigAdminService:
    """后台配置管理服务。

    负责 .env 文件的读写操作，将配置项元数据与 .env 中的实际值结合，
    为管理端前端提供结构化的配置数据，并接收前端提交的更新写回 .env。
    """

    def __init__(self, env_path: Optional[Path] = None) -> None:
        # 默认使用 backend/.env 文件
        self.env_path = env_path or Path(_BACKEND_DIR) / ".env"

    def get_config_payload(self) -> dict[str, Any]:
        """构建前端配置表单所需的完整载荷。

        读取 .env 中的原始值，逐个序列化为前端可用的结构（含类型、控件类型、当前值等）。
        返回分组列表 + 字段列表 + 重启提示信息。
        """
        raw_values = self._read_env_file()
        items = [self._serialize_item(field, raw_values.get(field.key)) for field in CONFIG_FIELDS]
        return {
            "groups": copy.deepcopy(CONFIG_GROUPS),
            "items": items,
            "restart_required": True,
            "message": "配置已保存，重启后端后生效。",
        }

    def update_config_values(self, values: dict[str, Any]) -> dict[str, Any]:
        """接收前端提交的配置更新，校验后写回 .env 文件。

        逐个字段校验：未知字段记录为错误，类型转换失败也记录为错误。
        若有任何错误则整体拒绝，抛出 ConfigValidationError。
        全部通过后将更新后的值写入 .env，保留未修改的行不变。
        """
        normalized: dict[str, str] = {}
        field_errors: dict[str, str] = {}

        for key, value in values.items():
            field = CONFIG_FIELD_MAP.get(key)
            if field is None:
                field_errors[key] = "不支持的配置项"
                continue
            try:
                parsed_value = self._coerce_value(field, value)
            except ValueError as exc:
                field_errors[key] = str(exc)
                continue
            # 将解析后的值格式化为 .env 文件中的字符串形式
            normalized[key] = self._format_for_env(field, parsed_value)

        if field_errors:
            raise ConfigValidationError(field_errors)

        self._write_env_file(normalized)
        return {
            "success": True,
            "message": "配置已保存，重启后端后生效。",
            "restart_required": True,
        }

    def _serialize_item(self, field: ConfigFieldMeta, raw_value: Optional[str]) -> dict[str, Any]:
        """将单个配置字段序列化为前端可用的字典结构。

        包含 key、分组、标签、描述、控件类型、当前解析值等信息。
        CSV 类型且控件为 text 时自动升级为 textarea。
        """
        parsed = self._coerce_value(field, raw_value) if raw_value is not None else self._default_value(field)
        input_type = field.input_type
        # CSV 类型默认使用 textarea 控件，方便用户输入多行地址
        if field.parse_as == "csv" and input_type == "text":
            input_type = "textarea"
        return {
            "key": field.key,
            "group": field.group,
            "label": field.label,
            "description": field.description,
            "inputType": input_type,
            "parseAs": field.parse_as,
            "value": parsed,
            "sensitive": field.sensitive,
            "required": field.required,
            "restartRequired": field.restart_required,
            "placeholder": field.placeholder,
            "options": copy.deepcopy(field.options) if field.options else [],
        }

    def _default_value(self, field: ConfigFieldMeta) -> Any:
        """获取配置字段的默认值。

        优先使用字段定义的 default；若未定义则根据 parse_as 类型返回零值（False/0/0.0/""）。
        """
        if field.default is not None:
            return field.default
        if field.parse_as == "bool":
            return False
        if field.parse_as == "int":
            return 0
        if field.parse_as == "float":
            return 0.0
        return ""

    def _coerce_value(self, field: ConfigFieldMeta, value: Any) -> Any:
        """将任意输入值按字段定义的 parse_as 类型转换为 Python 原生类型。

        支持的转换：
        - bool: 接受 bool、"true"/"false"/"1"/"0"/"yes"/"no"/"on"/"off" 字符串
        - int: 接受 int 或可解析的字符串
        - float: 接受 int/float 或可解析的字符串
        - csv: 列表用逗号拼接，字符串直接 trim
        - 其余类型: 转为字符串

        转换失败时抛出 ValueError，由调用方捕获并记录为字段错误。
        """
        if field.parse_as == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"1", "true", "yes", "on"}:
                    return True
                if normalized in {"0", "false", "no", "off"}:
                    return False
            raise ValueError("请输入 true/false 布尔值")

        if field.parse_as == "int":
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    return int(value.strip())
                except ValueError as exc:
                    raise ValueError("请输入合法整数") from exc
            raise ValueError("请输入合法整数")

        if field.parse_as == "float":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            if isinstance(value, str) and value.strip():
                try:
                    return float(value.strip())
                except ValueError as exc:
                    raise ValueError("请输入合法数字") from exc
            raise ValueError("请输入合法数字")

        if field.parse_as == "csv":
            if isinstance(value, list):
                return ",".join(str(item).strip() for item in value if str(item).strip())
            if value is None:
                return ""
            return str(value).strip()

        # string / url / path 等类型直接转字符串
        if value is None:
            return ""
        return str(value)

    def _format_for_env(self, field: ConfigFieldMeta, value: Any) -> str:
        """将解析后的 Python 值格式化为 .env 文件中使用的字符串。

        - bool: "true"/"false"
        - int/float: 转为字符串，浮点数去除尾随零
        - 其余: 直接 str()
        """
        if field.parse_as == "bool":
            return "true" if value else "false"
        if field.parse_as == "int":
            return str(int(value))
        if field.parse_as == "float":
            return str(float(value)).rstrip("0").rstrip(".") if "." in str(float(value)) else str(float(value))
        if field.parse_as == "csv":
            return str(value)
        return str(value)

    def _read_env_file(self) -> dict[str, str]:
        """读取 .env 文件，返回 key=value 字典。

        跳过空行和注释行（以 # 开头）。
        仅按第一个 "=" 分割，值中允许包含 "="。
        若文件不存在则返回空字典。
        """
        if not self.env_path.exists():
            return {}
        values: dict[str, str] = {}
        for line in self.env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _write_env_file(self, updates: dict[str, str]) -> None:
        """将更新写回 .env 文件，保留原有注释和未修改的行。

        策略：
        1. 逐行扫描原文件，遇到待更新的 key 则替换为新值
        2. 原文件中不存在的 key 追加到文件末尾（按 CONFIG_FIELDS 定义顺序）
        3. 保留注释行和空行的原始格式
        """
        original_lines: list[str] = []
        if self.env_path.exists():
            original_lines = self.env_path.read_text(encoding="utf-8").splitlines()

        # 待写入的更新，每处理一个就 pop，剩余的追加到末尾
        remaining = dict(updates)
        new_lines: list[str] = []
        for line in original_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in line:
                key, _ = line.split("=", 1)
                normalized_key = key.strip()
                if normalized_key in remaining:
                    # 替换为新值
                    new_lines.append(f"{normalized_key}={remaining.pop(normalized_key)}")
                    continue
            # 保留注释行、空行和未修改的配置行
            new_lines.append(line)

        # 追加原文件中不存在的新配置项
        if remaining:
            if new_lines and new_lines[-1] != "":
                new_lines.append("")
            # 按 CONFIG_FIELDS 定义顺序追加，保持 .env 文件有序
            for field in CONFIG_FIELDS:
                if field.key in remaining:
                    new_lines.append(f"{field.key}={remaining.pop(field.key)}")

        self.env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def get_config_admin_service() -> ConfigAdminService:
    """工厂函数：创建 ConfigAdminService 实例。"""
    return ConfigAdminService()
