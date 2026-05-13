"""
运维与治理相关的 ORM 模型模块。

定义后台任务调度、批量导入、用户反馈和 worker 心跳四张表。
这些模型支撑系统的异步任务管理、质量监控和运维可观测性。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from .database import Base


class JobTask(Base):
    """后台任务记录模型。

    对应数据库表 job_tasks，记录每个异步任务的类型、状态、优先级和执行结果。
    支持任务锁机制（locked_by/locked_at）防止重复执行，
    以及自动重试（retry_count/max_retries）提升任务可靠性。
    """

    __tablename__ = "job_tasks"

    # 主键，UUID 字符串
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    # 任务类型，如 "doc_parse"、"vectorize"、"reindex" 等
    job_type = Column(String, nullable=False, index=True)
    # 任务状态：pending / running / completed / failed / cancelled
    status = Column(String, nullable=False, default="pending", index=True)
    # 优先级，数值越小优先级越高，默认 100
    priority = Column(Integer, nullable=False, default=100, index=True)
    # 任务输入参数（JSON 字符串）
    payload_json = Column(Text, nullable=True)
    # 任务执行结果（JSON 字符串）
    result_json = Column(Text, nullable=True)
    # 错误信息，任务失败时记录异常详情
    error_message = Column(Text, nullable=True)
    # 已重试次数
    retry_count = Column(Integer, nullable=False, default=0)
    # 最大重试次数，超过后标记为 failed
    max_retries = Column(Integer, nullable=False, default=2)
    # 当前持有任务锁的 worker ID
    locked_by = Column(String, nullable=True, index=True)
    # 任务锁的获取时间
    locked_at = Column(DateTime, nullable=True)
    # 关联的文档 ID（文档解析类任务使用）
    related_doc_id = Column(String, nullable=True, index=True)
    # 关联的批量导入批次 ID
    related_batch_id = Column(String, nullable=True, index=True)
    # 任务创建时间
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    # 任务开始执行时间
    started_at = Column(DateTime, nullable=True)
    # 任务完成时间（成功或失败）
    finished_at = Column(DateTime, nullable=True)


class ImportBatch(Base):
    """批量导入批次模型。

    对应数据库表 import_batches，记录一次批量文档导入的整体状态。
    一个批次包含多个文档，每个文档对应一条 DocumentRecord。
    """

    __tablename__ = "import_batches"

    # 主键，UUID 字符串
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    # 来源类型，如 "document"（文档）、"image"（图片）
    source_type = Column(String, nullable=False, default="document", index=True)
    # 批次状态：pending / processing / completed / failed / partial
    status = Column(String, nullable=False, default="pending", index=True)
    # 批次汇总信息（JSON 字符串），如总文件数、成功/失败数量
    summary_json = Column(Text, nullable=True)
    # 创建时间
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    # 最后更新时间
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AnswerFeedback(Base):
    """用户对 RAG 回答的反馈记录模型。

    对应数据库表 answer_feedback，存储用户对助手回答的评价。
    支持点赞/踩（rating）、问题类型标注和文本评论，
    同时保存当时的检索快照，便于后续分析和改进检索质量。
    """

    __tablename__ = "answer_feedback"

    # 主键，自增整数
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # 所属会话 ID（可为空，兼容匿名场景）
    session_id = Column(String, nullable=True, index=True)
    # 被评价的助手消息 ID，外键关联 chat_messages.id
    assistant_message_id = Column(
        Integer,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 评价类型：like（点赞）/ dislike（踩）
    rating = Column(String, nullable=False, index=True)
    # 问题类型标签（JSON 数组字符串），如 ["不相关", "信息过时"]
    issue_types_json = Column(Text, nullable=True)
    # 用户自由评论文本
    comment = Column(Text, nullable=True)
    # 原始用户查询（快照），便于不关联上下文即可分析
    query = Column(Text, nullable=True)
    # 检索结果快照（JSON 字符串），记录当时的检索来源和排序
    retrieval_snapshot_json = Column(Text, nullable=True)
    # 反馈创建时间
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


class WorkerHeartbeat(Base):
    """后台 worker 心跳模型。

    对应数据库表 worker_heartbeats，每个 worker 以固定间隔更新心跳。
    运维端可通过心跳时间判断 worker 是否存活，details_json 可携带运行状态信息。
    """

    __tablename__ = "worker_heartbeats"

    # 主键，worker 的唯一标识符
    worker_id = Column(String, primary_key=True, index=True)
    # 运行状态详情（JSON 字符串），如队列积压数、内存占用等
    details_json = Column(Text, nullable=True)
    # 最后心跳更新时间，用于判断 worker 是否存活
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
