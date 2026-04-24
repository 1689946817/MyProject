"""
任务队列、反馈、批量导入与运行时状态服务。
"""
from __future__ import annotations

import json
import socket
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.chat_models import ChatMessage
from app.data.ops_models import AnswerFeedback, ImportBatch, JobTask, WorkerHeartbeat


VALID_JOB_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}
VALID_JOB_TYPES = {"document_parse", "document_reprocess", "batch_import"}
VALID_FEEDBACK_RATINGS = {"up", "down"}


def dump_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def load_json_dict(value: Optional[str]) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def load_json_list(value: Optional[str]) -> list[Any]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return loaded if isinstance(loaded, list) else []


def create_job(
    db: Session,
    *,
    job_type: str,
    payload: Optional[dict[str, Any]] = None,
    priority: int = 100,
    max_retries: int = 2,
    related_doc_id: Optional[str] = None,
    related_batch_id: Optional[str] = None,
) -> JobTask:
    if job_type not in VALID_JOB_TYPES:
        raise ValueError(f"unsupported job_type: {job_type}")
    job = JobTask(
        job_type=job_type,
        status="pending",
        priority=priority,
        payload_json=dump_json(payload or {}),
        max_retries=max(0, int(max_retries)),
        related_doc_id=related_doc_id,
        related_batch_id=related_batch_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job_or_raise(db: Session, job_id: str) -> JobTask:
    job = db.query(JobTask).filter(JobTask.id == job_id).first()
    if job is None:
        raise LookupError("任务不存在")
    return job


def list_jobs(
    db: Session,
    *,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[JobTask]:
    query = db.query(JobTask)
    if status:
        query = query.filter(JobTask.status == status)
    if job_type:
        query = query.filter(JobTask.job_type == job_type)
    return (
        query.order_by(JobTask.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def claim_next_job(db: Session, *, worker_id: str) -> Optional[JobTask]:
    now = datetime.now(timezone.utc)
    job = (
        db.query(JobTask)
        .filter(JobTask.status == "pending")
        .order_by(JobTask.priority.asc(), JobTask.created_at.asc())
        .first()
    )
    if job is None:
        return None
    job.status = "running"
    job.locked_by = worker_id
    job.locked_at = now
    job.started_at = now
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def complete_job(db: Session, job: JobTask, *, result: Optional[dict[str, Any]] = None) -> JobTask:
    job.status = "completed"
    job.result_json = dump_json(result or {})
    job.error_message = None
    job.finished_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def fail_job(
    db: Session,
    job: JobTask,
    *,
    error_message: str,
    retryable: bool = False,
) -> JobTask:
    now = datetime.now(timezone.utc)
    if retryable and job.retry_count < job.max_retries:
        job.status = "pending"
        job.retry_count += 1
        job.locked_by = None
        job.locked_at = None
        job.started_at = None
        job.finished_at = None
    else:
        job.status = "failed"
        job.finished_at = now
    job.error_message = error_message
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def retry_job(db: Session, job: JobTask) -> JobTask:
    if job.status not in {"failed", "cancelled"}:
        raise ValueError("仅失败或已取消任务可重试")
    job.status = "pending"
    job.error_message = None
    job.locked_by = None
    job.locked_at = None
    job.started_at = None
    job.finished_at = None
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_import_batch(db: Session, *, source_type: str = "document") -> ImportBatch:
    batch = ImportBatch(source_type=source_type, status="pending", summary_json=dump_json({}))
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def refresh_import_batch_summary(db: Session, batch: ImportBatch) -> ImportBatch:
    rows = (
        db.query(JobTask.status, func.count(JobTask.id))
        .filter(JobTask.related_batch_id == batch.id)
        .group_by(JobTask.status)
        .all()
    )
    summary = {status: count for status, count in rows}
    total = sum(summary.values())
    if total == 0:
        batch.status = "pending"
    elif summary.get("running"):
        batch.status = "running"
    elif summary.get("pending"):
        batch.status = "pending"
    elif summary.get("failed"):
        batch.status = "failed"
    else:
        batch.status = "completed"
    batch.summary_json = dump_json(
        {
            "total": total,
            "pending": summary.get("pending", 0),
            "running": summary.get("running", 0),
            "completed": summary.get("completed", 0),
            "failed": summary.get("failed", 0),
            "cancelled": summary.get("cancelled", 0),
        }
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def get_import_batch_or_raise(db: Session, batch_id: str) -> ImportBatch:
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if batch is None:
        raise LookupError("批次不存在")
    return batch


def record_feedback(
    db: Session,
    *,
    assistant_message: ChatMessage,
    rating: str,
    issue_types: Optional[list[str]] = None,
    comment: Optional[str] = None,
    query: Optional[str] = None,
    retrieval_snapshot: Optional[dict[str, Any]] = None,
) -> AnswerFeedback:
    if rating not in VALID_FEEDBACK_RATINGS:
        raise ValueError(f"unsupported rating: {rating}")
    feedback = AnswerFeedback(
        session_id=assistant_message.session_id,
        assistant_message_id=assistant_message.id,
        rating=rating,
        issue_types_json=dump_json(issue_types or []),
        comment=comment,
        query=query,
        retrieval_snapshot_json=dump_json(retrieval_snapshot or {}),
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def get_feedback_for_message(db: Session, assistant_message_id: int) -> Optional[AnswerFeedback]:
    return (
        db.query(AnswerFeedback)
        .filter(AnswerFeedback.assistant_message_id == assistant_message_id)
        .order_by(AnswerFeedback.created_at.desc())
        .first()
    )


def record_worker_heartbeat(
    db: Session,
    *,
    worker_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> WorkerHeartbeat:
    resolved_worker_id = worker_id or f"{socket.gethostname()}-worker"
    heartbeat = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker_id == resolved_worker_id).first()
    if heartbeat is None:
        heartbeat = WorkerHeartbeat(worker_id=resolved_worker_id)
    heartbeat.updated_at = datetime.now(timezone.utc)
    heartbeat.details_json = dump_json(details or {})
    db.add(heartbeat)
    db.commit()
    db.refresh(heartbeat)
    return heartbeat


def get_recent_worker_heartbeats(db: Session, *, within_seconds: int = 300) -> list[WorkerHeartbeat]:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
    return (
        db.query(WorkerHeartbeat)
        .filter(WorkerHeartbeat.updated_at >= cutoff)
        .order_by(WorkerHeartbeat.updated_at.desc())
        .all()
    )
