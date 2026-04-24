"""
运行与治理相关的 ORM 模型。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from .database import Base


class JobTask(Base):
    """后台任务记录。"""

    __tablename__ = "job_tasks"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    job_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    priority = Column(Integer, nullable=False, default=100, index=True)
    payload_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=2)
    locked_by = Column(String, nullable=True, index=True)
    locked_at = Column(DateTime, nullable=True)
    related_doc_id = Column(String, nullable=True, index=True)
    related_batch_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class ImportBatch(Base):
    """批量导入批次。"""

    __tablename__ = "import_batches"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    source_type = Column(String, nullable=False, default="document", index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    summary_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AnswerFeedback(Base):
    """回答反馈记录。"""

    __tablename__ = "answer_feedback"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String, nullable=True, index=True)
    assistant_message_id = Column(
        Integer,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating = Column(String, nullable=False, index=True)
    issue_types_json = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)
    query = Column(Text, nullable=True)
    retrieval_snapshot_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


class WorkerHeartbeat(Base):
    """后台 worker 心跳。"""

    __tablename__ = "worker_heartbeats"

    worker_id = Column(String, primary_key=True, index=True)
    details_json = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
