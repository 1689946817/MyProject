"""
任务队列、反馈、批量导入与运行时状态服务。

架构角色：应用层操作服务，提供任务生命周期管理（创建/领取/完成/失败/重试）、
批量导入批次跟踪、用户反馈记录、Worker 心跳监控等功能。

核心导出：
- 任务管理：create_job, claim_next_job, complete_job, fail_job, retry_job, list_jobs
- 批量导入：create_import_batch, refresh_import_batch_summary
- 反馈记录：record_feedback, get_feedback_for_message
- 心跳监控：record_worker_heartbeat, get_recent_worker_heartbeats
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

# ---- 常量定义 ----
VALID_JOB_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}  # 任务合法状态集合
VALID_JOB_TYPES = {"document_parse", "document_reprocess", "batch_import"}        # 任务合法类型集合
VALID_FEEDBACK_RATINGS = {"up", "down"}  # 反馈合法评分（点赞/踩）


# ---- JSON 序列化/反序列化工具 ----

def dump_json(value: Any) -> Optional[str]:
    """将任意值序列化为 JSON 字符串，保留中文等非 ASCII 字符。None 返回 None。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def load_json_dict(value: Optional[str]) -> dict[str, Any]:
    """将 JSON 字符串解析为字典；解析失败或类型不匹配时返回空字典。"""
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def load_json_list(value: Optional[str]) -> list[Any]:
    """将 JSON 字符串解析为列表；解析失败或类型不匹配时返回空列表。"""
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return loaded if isinstance(loaded, list) else []


# ---- 任务生命周期管理 ----

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
    """创建新任务并持久化到数据库。

    Args:
        db: 数据库会话
        job_type: 任务类型，必须在 VALID_JOB_TYPES 中
        payload: 任务参数字典，序列化后存入 payload_json
        priority: 优先级，数值越小优先级越高，默认 100
        max_retries: 最大重试次数，默认 2
        related_doc_id: 关联的文档 ID
        related_batch_id: 关联的批量导入批次 ID

    Returns:
        新创建的 JobTask 对象

    Raises:
        ValueError: job_type 不在合法集合中
    """
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
    """根据 ID 查询任务，不存在时抛出 LookupError。"""
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
    """分页查询任务列表，支持按状态和类型过滤，按创建时间倒序。"""
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
    """按优先级（升序）+ 创建时间（升序）领取下一个 pending 任务。

    领取操作将任务状态置为 running，记录 worker_id 和锁定时间。
    注意：此处依赖数据库层面的行锁（SQLAlchemy 默认事务隔离），
    不同 worker 可能领取到同一个 pending 任务——需配合外部锁或单 worker 模式使用。

    Args:
        db: 数据库会话
        worker_id: 领取任务的 worker 标识

    Returns:
        领取到的任务，无待处理任务时返回 None
    """
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
    """将任务标记为完成，写入结果 JSON 并记录完成时间。"""
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
    """将任务标记为失败。

    如果 retryable=True 且重试次数未超限，则将任务重置为 pending 状态
    并递增 retry_count，供后续再次领取；否则置为 failed 并记录结束时间。

    Args:
        db: 数据库会话
        job: 失败的任务对象
        error_message: 错误信息
        retryable: 是否允许自动重试

    Returns:
        更新后的任务对象
    """
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
    """手动重试任务，仅允许对 failed 或 cancelled 状态的任务操作。

    重置任务为 pending 状态，清除所有锁定/错误信息。

    Raises:
        ValueError: 任务状态不在 {failed, cancelled} 中
    """
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


# ---- 批量导入批次管理 ----

def create_import_batch(db: Session, *, source_type: str = "document") -> ImportBatch:
    """创建新的批量导入批次，默认 source_type 为 "document"。"""
    batch = ImportBatch(source_type=source_type, status="pending", summary_json=dump_json({}))
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def refresh_import_batch_summary(db: Session, batch: ImportBatch) -> ImportBatch:
    """刷新批量导入批次的汇总状态。

    查询该批次下所有关联任务的按状态分组计数，推导批次整体状态：
    - 有 running 任务 -> "running"
    - 有 pending 任务 -> "pending"
    - 有 failed 任务（且无 running/pending） -> "failed"
    - 全部 completed -> "completed"
    - 无任务 -> "pending"

    Returns:
        更新后的 ImportBatch 对象
    """
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
    """根据 ID 查询批次，不存在时抛出 LookupError。"""
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if batch is None:
        raise LookupError("批次不存在")
    return batch


# ---- 用户反馈管理 ----

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
    """记录用户对助手回答的反馈。

    Args:
        db: 数据库会话
        assistant_message: 被评价的助手消息对象
        rating: 评分，"up" 或 "down"
        issue_types: 问题类型列表（如 "incorrect", "irrelevant"）
        comment: 用户自由评论文本
        query: 原始查询文本，便于回溯
        retrieval_snapshot: 检索结果快照，用于复现调试

    Returns:
        新创建的 AnswerFeedback 对象

    Raises:
        ValueError: rating 不在合法集合中
    """
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
    """查询指定助手消息的最新一条反馈（按创建时间倒序）。"""
    return (
        db.query(AnswerFeedback)
        .filter(AnswerFeedback.assistant_message_id == assistant_message_id)
        .order_by(AnswerFeedback.created_at.desc())
        .first()
    )


# ---- Worker 心跳监控 ----

def record_worker_heartbeat(
    db: Session,
    *,
    worker_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> WorkerHeartbeat:
    """记录或更新 worker 心跳。

    如果 worker_id 已存在则更新其时间戳和详情，否则创建新记录。
    未指定 worker_id 时使用 "{hostname}-worker" 作为默认标识。

    Args:
        db: 数据库会话
        worker_id: worker 标识，默认为主机名 + "-worker"
        details: 可选的运行时详情（如队列深度、内存使用等）

    Returns:
        创建或更新后的 WorkerHeartbeat 对象
    """
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
    """查询最近指定秒数内有心跳的活跃 worker 列表。

    Args:
        db: 数据库会话
        within_seconds: 心跳有效期，默认 300 秒（5 分钟）

    Returns:
        按更新时间倒序排列的活跃 WorkerHeartbeat 列表
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
    return (
        db.query(WorkerHeartbeat)
        .filter(WorkerHeartbeat.updated_at >= cutoff)
        .order_by(WorkerHeartbeat.updated_at.desc())
        .all()
    )
