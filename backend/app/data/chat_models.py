"""
聊天会话与消息 ORM 模型模块。

定义 chat_sessions（会话）和 chat_messages（消息）两张数据库表的映射关系。
会话与消息为一对多关系：一个会话包含多条消息，删除会话时级联删除所有消息。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class ChatSession(Base):
    """聊天会话模型。

    对应数据库表 chat_sessions，记录一次多轮对话的元信息。
    每个会话有一个 UUID 主键和可选标题，前端据此展示会话列表。
    """

    __tablename__ = "chat_sessions"

    # 主键，UUID 字符串，创建时自动生成
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    # 会话标题，可为空（前端可从首条用户消息截取）
    title = Column(String, nullable=True)
    # 创建时间，UTC 时区
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    # 最后更新时间，每次修改时自动更新
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 一对多关系：该会话下的所有消息
    # cascade="all, delete-orphan" 表示删除会话时自动删除所有关联消息
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    """聊天消息模型。

    对应数据库表 chat_messages，记录单条聊天消息的完整内容。
    支持存储 RAG 检索结果（sources_json）、检索参数和检索步骤，
    便于前端还原对话历史和调试检索过程。
    """

    __tablename__ = "chat_messages"

    # 主键，自增整数
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # 所属会话 ID，外键关联 chat_sessions.id，级联删除
    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    # 消息角色："user"（用户）或 "assistant"（助手）
    role = Column(String, nullable=False)
    # 消息正文内容
    content = Column(Text, nullable=False)
    # 是否包含图片（助手消息可能附带检索到的图片）
    has_image = Column(Boolean, nullable=False, default=False)
    # 检索到的来源信息（JSON 字符串），包含图片 ID、描述、相似度等
    sources_json = Column(Text, nullable=True)
    # 检索参数快照（JSON 字符串），如 top_k、重排配置等
    retrieval_params_json = Column(Text, nullable=True)
    # 检索步骤详情（JSON 字符串），记录各阶段耗时和中间结果
    retrieval_steps_json = Column(Text, nullable=True)
    # 消息创建时间，UTC 时区
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # 多对一关系：关联到所属会话
    session = relationship("ChatSession", back_populates="messages")
