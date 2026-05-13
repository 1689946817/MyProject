"""知识库管理服务。

架构角色：应用层知识资产管理，提供图片/文档记录的管理列自动迁移、
启用/禁用过滤、安全文件删除、标签/元数据序列化等能力。

核心导出：
- 迁移工具：ensure_knowledge_management_columns（确保管理字段存在）
- 过滤服务：filter_enabled_image_hit_dicts, filter_enabled_image_documents,
            filter_enabled_text_chunk_hits
- 查询工具：get_image_record_or_raise, get_document_record_or_raise, get_document_image_records
- 文件清理：safe_unlink（带路径白名单的安全删除）
"""
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from langchain_core.documents import Document

from app.data.database import SessionLocal
from app.data.doc_models import DocumentRecord
from app.data.models import ImageRecord
from app.data.storage import BASE_STORAGE_DIR, DOC_STORAGE_DIR


logger = logging.getLogger(__name__)

ALLOWED_DOCUMENT_TYPES = {"pdf", "markdown"}  # 支持的文档类型白名单


# ---- Schema 迁移：自动补全管理字段 ----

def ensure_image_management_columns(db: Session) -> None:
    """确保 image_records 表包含所有知识管理所需字段。

    通过检查当前表结构，对缺失字段执行 ALTER TABLE ADD COLUMN。
    补充的字段包括：title, notes, enabled, custom_metadata, parent_doc_id,
    content_hash, logical_asset_id, version_number, is_latest。
    已存在的字段会被跳过，避免重复 DDL 错误。
    """
    inspector = inspect(db.bind)
    columns = {column["name"] for column in inspector.get_columns("image_records")}
    statements = {
        "title": "ALTER TABLE image_records ADD COLUMN title TEXT",
        "notes": "ALTER TABLE image_records ADD COLUMN notes TEXT",
        "enabled": "ALTER TABLE image_records ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1",
        "custom_metadata": "ALTER TABLE image_records ADD COLUMN custom_metadata TEXT",
        "parent_doc_id": "ALTER TABLE image_records ADD COLUMN parent_doc_id TEXT",
        "content_hash": "ALTER TABLE image_records ADD COLUMN content_hash TEXT",
        "logical_asset_id": "ALTER TABLE image_records ADD COLUMN logical_asset_id TEXT",
        "version_number": "ALTER TABLE image_records ADD COLUMN version_number INTEGER NOT NULL DEFAULT 1",
        "is_latest": "ALTER TABLE image_records ADD COLUMN is_latest BOOLEAN NOT NULL DEFAULT 1",
    }
    for column, ddl in statements.items():
        if column in columns:
            continue
        db.execute(text(ddl))
        db.commit()


def ensure_document_management_columns(db: Session) -> None:
    """确保 document_records 表包含所有知识管理所需字段。

    补充的字段包括：title, document_type, tags, notes, enabled, custom_metadata,
    parse_backend, parse_stage, progress_percent, progress_message,
    content_hash, logical_asset_id, version_number, is_latest。
    """
    inspector = inspect(db.bind)
    columns = {column["name"] for column in inspector.get_columns("document_records")}
    statements = {
        "title": "ALTER TABLE document_records ADD COLUMN title TEXT",
        "document_type": "ALTER TABLE document_records ADD COLUMN document_type TEXT NOT NULL DEFAULT 'pdf'",
        "tags": "ALTER TABLE document_records ADD COLUMN tags TEXT",
        "notes": "ALTER TABLE document_records ADD COLUMN notes TEXT",
        "enabled": "ALTER TABLE document_records ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1",
        "custom_metadata": "ALTER TABLE document_records ADD COLUMN custom_metadata TEXT",
        "parse_backend": "ALTER TABLE document_records ADD COLUMN parse_backend TEXT NOT NULL DEFAULT 'local'",
        "parse_stage": "ALTER TABLE document_records ADD COLUMN parse_stage TEXT NOT NULL DEFAULT 'queued'",
        "progress_percent": "ALTER TABLE document_records ADD COLUMN progress_percent INTEGER NOT NULL DEFAULT 0",
        "progress_message": "ALTER TABLE document_records ADD COLUMN progress_message TEXT",
        "content_hash": "ALTER TABLE document_records ADD COLUMN content_hash TEXT",
        "logical_asset_id": "ALTER TABLE document_records ADD COLUMN logical_asset_id TEXT",
        "version_number": "ALTER TABLE document_records ADD COLUMN version_number INTEGER NOT NULL DEFAULT 1",
        "is_latest": "ALTER TABLE document_records ADD COLUMN is_latest BOOLEAN NOT NULL DEFAULT 1",
    }
    for column, ddl in statements.items():
        if column in columns:
            continue
        db.execute(text(ddl))
        db.commit()


def ensure_knowledge_management_columns(db: Session) -> None:
    """统一入口：同时确保图片和文档两张表的管理字段完整。"""
    ensure_image_management_columns(db)
    ensure_document_management_columns(db)


# ---- 标签与 JSON 序列化工具 ----

def dump_tags(tags: Optional[Iterable[str]]) -> Optional[str]:
    """将标签迭代器序列化为逗号分隔字符串，过滤空白标签。None 返回 None。"""
    if tags is None:
        return None
    normalized = [str(tag).strip() for tag in tags if str(tag).strip()]
    return ",".join(normalized)


def load_tags(tags: Optional[str]) -> list[str]:
    """将逗号分隔的标签字符串还原为列表，过滤空白项。"""
    if not tags:
        return []
    return [item.strip() for item in tags.split(",") if item.strip()]


def dump_json_dict(data: Optional[dict[str, Any]]) -> Optional[str]:
    """将字典序列化为 JSON 字符串。None 返回 None。"""
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False)


def load_json_dict(data: Optional[str]) -> dict[str, Any]:
    """将 JSON 字符串解析为字典；解析失败或类型不匹配时返回空字典。"""
    if not data:
        return {}
    try:
        loaded = json.loads(data)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def validate_document_type(document_type: Optional[str]) -> Optional[str]:
    """校验文档类型是否在白名单内，返回标准化后的小写类型名。

    Raises:
        ValueError: 文档类型不在 ALLOWED_DOCUMENT_TYPES 中
    """
    if document_type is None:
        return None
    normalized = document_type.strip().lower()
    if normalized not in ALLOWED_DOCUMENT_TYPES:
        raise ValueError(f"unsupported document_type: {document_type}")
    return normalized


# ---- 记录查询工具 ----

def get_image_record_or_raise(db: Session, image_id: str) -> ImageRecord:
    """查询图片记录，不存在时抛出 LookupError。查询前自动确保管理字段存在。"""
    ensure_knowledge_management_columns(db)
    record = db.query(ImageRecord).filter(ImageRecord.id == image_id).first()
    if record is None:
        raise LookupError("图片不存在")
    return record


def get_document_record_or_raise(db: Session, doc_id: str) -> DocumentRecord:
    """查询文档记录，不存在时抛出 LookupError。"""
    ensure_knowledge_management_columns(db)
    record = db.query(DocumentRecord).filter(DocumentRecord.id == doc_id).first()
    if record is None:
        raise LookupError("文档不存在")
    return record


def get_document_image_records(db: Session, doc_id: str) -> list[ImageRecord]:
    """查询指定文档关联的所有图片记录。

    优先通过 parent_doc_id 精确匹配；若无结果，则回退到在 extra_metadata JSON
    中查找 "doc_id" 字段匹配的记录（兼容旧数据）。
    """
    ensure_knowledge_management_columns(db)
    explicit_matches = db.query(ImageRecord).filter(ImageRecord.parent_doc_id == doc_id).all()
    if explicit_matches:
        return explicit_matches
    candidates = db.query(ImageRecord).filter(ImageRecord.extra_metadata.contains(doc_id)).all()
    related: list[ImageRecord] = []
    for record in candidates:
        metadata = load_json_dict(record.extra_metadata)
        if metadata.get("doc_id") == doc_id:
            related.append(record)
    return related


# ---- 安全文件删除 ----

def safe_unlink(path_str: Optional[str]) -> bool:
    """安全删除文件，仅允许删除存储目录内的文件。

    路径必须位于 BASE_STORAGE_DIR 或 DOC_STORAGE_DIR 内，
    否则抛出 ValueError 防止目录穿越攻击。

    Args:
        path_str: 文件路径字符串

    Returns:
        True 表示删除成功，False 表示路径为空或文件不存在

    Raises:
        ValueError: 路径不在允许的存储目录内
    """
    if not path_str:
        return False
    path = Path(path_str)
    if not path.exists():
        return False

    resolved = path.resolve()
    allowed_roots = [
        BASE_STORAGE_DIR.resolve(),
        DOC_STORAGE_DIR.resolve(),
    ]
    if not any(root in resolved.parents or resolved == root for root in allowed_roots):
        raise ValueError(f"refuse to delete path outside storage roots: {resolved}")

    resolved.unlink()
    return True


# ---- 启用/禁用过滤服务 ----

def filter_enabled_image_hit_dicts(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """过滤检索结果中的图片命中，仅保留启用状态的图片。

    过滤逻辑：
    1. 查询所有命中的 ImageRecord，检查 enabled 字段
    2. 对有 parent_doc_id 的图片，检查父文档是否启用
    3. 被禁用的图片或其父文档被禁用的图片均会被过滤掉

    Args:
        hits: 检索返回的图片命中字典列表，每个字典需包含 "id" 字段

    Returns:
        过滤后的命中列表，仅包含启用状态的图片
    """
    if not hits:
        return []

    ids = [str(hit.get("id", "")).strip() for hit in hits if str(hit.get("id", "")).strip()]
    if not ids:
        return []

    with SessionLocal() as db:
        ensure_knowledge_management_columns(db)
        records = db.query(ImageRecord).filter(ImageRecord.id.in_(ids)).all()
        image_map = {record.id: record for record in records}

        parent_doc_ids: set[str] = set()
        image_doc_map: dict[str, Optional[str]] = {}
        for image_id, record in image_map.items():
            doc_id = getattr(record, "parent_doc_id", None)
            if not doc_id:
                metadata = load_json_dict(record.extra_metadata)
                doc_id = metadata.get("doc_id")
            image_doc_map[image_id] = doc_id
            if isinstance(doc_id, str) and doc_id:
                parent_doc_ids.add(doc_id)

        enabled_docs = set()
        if parent_doc_ids:
            enabled_docs = {
                item.id
                for item in db.query(DocumentRecord).filter(
                    DocumentRecord.id.in_(list(parent_doc_ids)),
                    DocumentRecord.enabled.is_(True),
                ).all()
            }

        filtered: list[dict[str, Any]] = []
        for hit in hits:
            image_id = str(hit.get("id", "")).strip()
            record = image_map.get(image_id)
            if record is None or not bool(getattr(record, "enabled", True)):
                continue
            parent_doc_id = image_doc_map.get(image_id)
            if parent_doc_id and parent_doc_id not in enabled_docs:
                continue
            filtered.append(hit)
        return filtered


def filter_enabled_image_documents(documents: list[Document]) -> list[Document]:
    """过滤 LangChain Document 列表中的图片文档，仅保留启用状态的。

    将 Document 转换为 hit dict 格式后复用 filter_enabled_image_hit_dicts 逻辑。
    """
    if not documents:
        return []
    hits = [
        {
            "id": doc.metadata.get("id", ""),
            "document": doc.page_content,
            "metadata": doc.metadata,
        }
        for doc in documents
    ]
    allowed = filter_enabled_image_hit_dicts(hits)
    allowed_ids = {item["id"] for item in allowed}
    return [doc for doc in documents if doc.metadata.get("id") in allowed_ids]


def filter_enabled_text_chunk_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """过滤文本分块检索结果，仅保留所属文档为启用状态的命中。

    每个 hit 需包含 "doc_id" 字段用于关联父文档。
    若无 doc_id 字段则原样返回（无法关联文档状态）。
    """
    if not hits:
        return []
    doc_ids = {
        str(hit.get("doc_id", "")).strip()
        for hit in hits
        if str(hit.get("doc_id", "")).strip()
    }
    if not doc_ids:
        return hits

    with SessionLocal() as db:
        ensure_knowledge_management_columns(db)
        enabled_doc_ids = {
            item.id
            for item in db.query(DocumentRecord).filter(
                DocumentRecord.id.in_(list(doc_ids)),
                DocumentRecord.enabled.is_(True),
            ).all()
        }
    return [hit for hit in hits if hit.get("doc_id") in enabled_doc_ids]
