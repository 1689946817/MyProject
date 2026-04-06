"""知识库管理服务。"""
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

ALLOWED_DOCUMENT_TYPES = {"pdf", "markdown"}


def ensure_image_management_columns(db: Session) -> None:
    inspector = inspect(db.bind)
    columns = {column["name"] for column in inspector.get_columns("image_records")}
    statements = {
        "title": "ALTER TABLE image_records ADD COLUMN title TEXT",
        "notes": "ALTER TABLE image_records ADD COLUMN notes TEXT",
        "enabled": "ALTER TABLE image_records ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1",
        "custom_metadata": "ALTER TABLE image_records ADD COLUMN custom_metadata TEXT",
    }
    for column, ddl in statements.items():
        if column in columns:
            continue
        db.execute(text(ddl))
        db.commit()


def ensure_document_management_columns(db: Session) -> None:
    inspector = inspect(db.bind)
    columns = {column["name"] for column in inspector.get_columns("document_records")}
    statements = {
        "title": "ALTER TABLE document_records ADD COLUMN title TEXT",
        "document_type": "ALTER TABLE document_records ADD COLUMN document_type TEXT NOT NULL DEFAULT 'pdf'",
        "tags": "ALTER TABLE document_records ADD COLUMN tags TEXT",
        "notes": "ALTER TABLE document_records ADD COLUMN notes TEXT",
        "enabled": "ALTER TABLE document_records ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1",
        "custom_metadata": "ALTER TABLE document_records ADD COLUMN custom_metadata TEXT",
    }
    for column, ddl in statements.items():
        if column in columns:
            continue
        db.execute(text(ddl))
        db.commit()


def ensure_knowledge_management_columns(db: Session) -> None:
    ensure_image_management_columns(db)
    ensure_document_management_columns(db)


def dump_tags(tags: Optional[Iterable[str]]) -> Optional[str]:
    if tags is None:
        return None
    normalized = [str(tag).strip() for tag in tags if str(tag).strip()]
    return ",".join(normalized)


def load_tags(tags: Optional[str]) -> list[str]:
    if not tags:
        return []
    return [item.strip() for item in tags.split(",") if item.strip()]


def dump_json_dict(data: Optional[dict[str, Any]]) -> Optional[str]:
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False)


def load_json_dict(data: Optional[str]) -> dict[str, Any]:
    if not data:
        return {}
    try:
        loaded = json.loads(data)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def validate_document_type(document_type: Optional[str]) -> Optional[str]:
    if document_type is None:
        return None
    normalized = document_type.strip().lower()
    if normalized not in ALLOWED_DOCUMENT_TYPES:
        raise ValueError(f"unsupported document_type: {document_type}")
    return normalized


def get_image_record_or_raise(db: Session, image_id: str) -> ImageRecord:
    ensure_knowledge_management_columns(db)
    record = db.query(ImageRecord).filter(ImageRecord.id == image_id).first()
    if record is None:
        raise LookupError("图片不存在")
    return record


def get_document_record_or_raise(db: Session, doc_id: str) -> DocumentRecord:
    ensure_knowledge_management_columns(db)
    record = db.query(DocumentRecord).filter(DocumentRecord.id == doc_id).first()
    if record is None:
        raise LookupError("文档不存在")
    return record


def get_document_image_records(db: Session, doc_id: str) -> list[ImageRecord]:
    ensure_knowledge_management_columns(db)
    candidates = db.query(ImageRecord).filter(ImageRecord.extra_metadata.contains(doc_id)).all()
    related: list[ImageRecord] = []
    for record in candidates:
        metadata = load_json_dict(record.extra_metadata)
        if metadata.get("doc_id") == doc_id:
            related.append(record)
    return related


def safe_unlink(path_str: Optional[str]) -> bool:
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


def filter_enabled_image_hit_dicts(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
