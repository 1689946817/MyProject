"""配置管理服务。"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from app.core.config import _BACKEND_DIR

ParseAs = Literal["string", "bool", "int", "float", "csv", "url", "path"]
InputType = Literal["text", "textarea", "password", "switch", "number", "select"]


class ConfigValidationError(Exception):
    """配置校验异常。"""

    def __init__(self, field_errors: dict[str, str], message: str = "配置校验失败") -> None:
        super().__init__(message)
        self.field_errors = field_errors
        self.message = message


@dataclass(frozen=True)
class ConfigFieldMeta:
    key: str
    group: str
    label: str
    description: str
    parse_as: ParseAs = "string"
    input_type: InputType = "text"
    sensitive: bool = False
    required: bool = False
    restart_required: bool = True
    placeholder: Optional[str] = None
    options: Optional[list[dict[str, str]]] = None
    default: Any = None


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
    return [{"label": value, "value": value} for value in values]


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
    ConfigFieldMeta("EMBEDDING_BASE_URL", "models", "向量模型地址", "文本向量模型 API 的基础 URL。", parse_as="url"),
    ConfigFieldMeta("EMBEDDING_API_KEY", "models", "向量模型密钥", "文本向量模型服务访问密钥。", sensitive=True, input_type="password"),
    ConfigFieldMeta("EMBEDDING_MODEL_NAME", "models", "向量模型名", "文本检索使用的 embedding 模型名称。"),
    ConfigFieldMeta("PADDLEOCR_PYTHON", "doc_parse", "PaddleOCR Python 路径", "OCR 子进程所使用的 Python 解释器路径。", parse_as="path"),
    ConfigFieldMeta("MULTIMODAL_EMBEDDING_API_KEY", "models", "多模态向量密钥", "图文同空间向量模型服务访问密钥。", sensitive=True, input_type="password"),
    ConfigFieldMeta("MULTIMODAL_EMBEDDING_MODEL_NAME", "models", "多模态向量模型名", "图文同空间向量模型名称。"),
    ConfigFieldMeta("LLM_BASE_URL", "models", "大语言模型地址", "RAG 生成回答所使用文本生成模型 API 地址。", parse_as="url"),
    ConfigFieldMeta("LLM_API_KEY", "models", "大语言模型密钥", "文本生成模型服务访问密钥。", sensitive=True, input_type="password"),
    ConfigFieldMeta("LLM_MODEL_NAME", "models", "大语言模型名", "RAG 回答生成使用的模型名称。"),
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
    ConfigFieldMeta("BM25_INDEX_PATH", "retrieval", "BM25 索引路径", "混合检索使用的 BM25 索引文件路径。", parse_as="path", default="storage/bm25_index.pkl"),
    ConfigFieldMeta("HYBRID_VECTOR_WEIGHT", "retrieval", "向量检索权重", "混合检索中向量得分的权重比例。", parse_as="float", input_type="number", default=0.6),
    ConfigFieldMeta("HYBRID_BM25_WEIGHT", "retrieval", "BM25 权重", "混合检索中 BM25 得分的权重比例。", parse_as="float", input_type="number", default=0.4),
    ConfigFieldMeta("CONTEXT_COMPRESSION_ENABLED", "rag", "启用上下文压缩", "开启后会对召回上下文进行压缩以减少提示长度。", parse_as="bool", input_type="switch", default=True),
    ConfigFieldMeta("CHAT_HISTORY_MAX_TURNS", "rag", "对话记忆轮数", "RAG 问答可参考的历史对话最大轮数。", parse_as="int", input_type="number", default=5),
    ConfigFieldMeta("AGENTIC_RAG_ENABLED", "rag", "启用 Agentic RAG", "开启后启用 Agentic RAG 流程。", parse_as="bool", input_type="switch", default=False),
    ConfigFieldMeta("EVAL_BASE_URL", "eval", "评测模型地址", "评测器调用的 OpenAI 兼容服务地址。", parse_as="url"),
    ConfigFieldMeta("EVAL_API_KEY", "eval", "评测模型密钥", "评测器服务访问密钥。", sensitive=True, input_type="password"),
    ConfigFieldMeta("EVAL_MODEL", "eval", "评测模型名", "离线评测使用的模型名称。"),
]

CONFIG_FIELD_MAP = {field.key: field for field in CONFIG_FIELDS}


class ConfigAdminService:
    """后台配置管理服务。"""

    def __init__(self, env_path: Optional[Path] = None) -> None:
        self.env_path = env_path or Path(_BACKEND_DIR) / ".env"

    def get_config_payload(self) -> dict[str, Any]:
        raw_values = self._read_env_file()
        items = [self._serialize_item(field, raw_values.get(field.key)) for field in CONFIG_FIELDS]
        return {
            "groups": copy.deepcopy(CONFIG_GROUPS),
            "items": items,
            "restart_required": True,
            "message": "配置已保存，重启后端后生效。",
        }

    def update_config_values(self, values: dict[str, Any]) -> dict[str, Any]:
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
        parsed = self._coerce_value(field, raw_value) if raw_value is not None else self._default_value(field)
        input_type = field.input_type
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

        if value is None:
            return ""
        return str(value)

    def _format_for_env(self, field: ConfigFieldMeta, value: Any) -> str:
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
        original_lines: list[str] = []
        if self.env_path.exists():
            original_lines = self.env_path.read_text(encoding="utf-8").splitlines()

        remaining = dict(updates)
        new_lines: list[str] = []
        for line in original_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in line:
                key, _ = line.split("=", 1)
                normalized_key = key.strip()
                if normalized_key in remaining:
                    new_lines.append(f"{normalized_key}={remaining.pop(normalized_key)}")
                    continue
            new_lines.append(line)

        if remaining:
            if new_lines and new_lines[-1] != "":
                new_lines.append("")
            for field in CONFIG_FIELDS:
                if field.key in remaining:
                    new_lines.append(f"{field.key}={remaining.pop(field.key)}")

        self.env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def get_config_admin_service() -> ConfigAdminService:
    return ConfigAdminService()
