"""
聊天会话服务。

提供聊天会话（ChatSession）和聊天消息（ChatMessage）的 CRUD 操作，
包括会话创建、列表查询、消息追加、历史获取等功能。
同时包含数据库迁移辅助函数，用于确保新增列存在于 SQLite 表中。
"""
import json
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.data.chat_models import ChatMessage, ChatSession


VALID_ROLES = {"user", "assistant"}  # 合法的消息角色集合


class ChatSessionNotFoundError(Exception):
    """会话不存在时抛出的异常。"""


def ensure_chat_sources_column(db: Session) -> None:
    """确保 chat_messages 表包含 sources_json 列。

    若列不存在则通过 ALTER TABLE 添加，用于数据库迁移兼容。
    """
    inspector = inspect(db.bind)
    columns = {column["name"] for column in inspector.get_columns("chat_messages")}
    if "sources_json" in columns:
        return
    db.execute(text("ALTER TABLE chat_messages ADD COLUMN sources_json TEXT"))
    db.commit()


def ensure_retrieval_params_column(db: Session) -> None:
    """确保 chat_messages 表包含 retrieval_params_json 列。

    若列不存在则通过 ALTER TABLE 添加，用于数据库迁移兼容。
    """
    inspector = inspect(db.bind)
    columns = {column["name"] for column in inspector.get_columns("chat_messages")}
    if "retrieval_params_json" in columns:
        return
    db.execute(text("ALTER TABLE chat_messages ADD COLUMN retrieval_params_json TEXT"))
    db.commit()


def ensure_retrieval_steps_column(db: Session) -> None:
    """确保 chat_messages 表包含 retrieval_steps_json 列。

    若列不存在则通过 ALTER TABLE 添加，用于数据库迁移兼容。
    """
    inspector = inspect(db.bind)
    columns = {column["name"] for column in inspector.get_columns("chat_messages")}
    if "retrieval_steps_json" in columns:
        return
    db.execute(text("ALTER TABLE chat_messages ADD COLUMN retrieval_steps_json TEXT"))
    db.commit()


def dump_message_sources(sources: Optional[List[dict[str, Any]]]) -> Optional[str]:
    """将消息来源列表序列化为 JSON 字符串。

    参数:
        sources: 来源字典列表，None 表示未传入。

    返回:
        JSON 字符串；None 输入返回 None，空列表返回 "[]"。
    """
    if sources is None:
        return None
    if not sources:
        return "[]"
    return json.dumps(sources, ensure_ascii=False)


def load_message_sources(sources_json: Optional[str]) -> List[dict[str, Any]]:
    """将 JSON 字符串反序列化为消息来源列表。

    参数:
        sources_json: JSON 字符串。

    返回:
        字典列表；解析失败时返回空列表。
    """
    if not sources_json:
        return []
    try:
        loaded = json.loads(sources_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def dump_json_list(data: Optional[List[dict[str, Any]]]) -> Optional[str]:
    """将字典列表序列化为 JSON 字符串。

    参数:
        data: 字典列表，None 表示未传入。

    返回:
        JSON 字符串；None 输入返回 None，空列表返回 "[]"。
    """
    if data is None:
        return None
    if not data:
        return "[]"
    return json.dumps(data, ensure_ascii=False)


def load_json_list(json_str: Optional[str]) -> List[dict[str, Any]]:
    """将 JSON 字符串反序列化为字典列表。

    参数:
        json_str: JSON 字符串。

    返回:
        字典列表；解析失败时返回空列表。
    """
    if not json_str:
        return []
    try:
        loaded = json.loads(json_str)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def dump_json_field(data: Optional[dict[str, Any]]) -> Optional[str]:
    """将字典序列化为 JSON 字符串。

    参数:
        data: 字典，None 表示未传入。

    返回:
        JSON 字符串；None 输入返回 None。
    """
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False)


def load_json_field(json_str: Optional[str]) -> Optional[dict[str, Any]]:
    """将 JSON 字符串反序列化为字典。

    参数:
        json_str: JSON 字符串。

    返回:
        解析后的字典；解析失败时返回 None。
    """
    if not json_str:
        return None
    try:
        loaded = json.loads(json_str)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded


def create_session(db: Session, title: Optional[str] = None) -> ChatSession:
    """创建新的聊天会话。

    参数:
        db: 数据库会话。
        title: 可选的会话标题。

    返回:
        新创建的 ChatSession 对象。
    """
    ensure_chat_sources_column(db)
    ensure_retrieval_params_column(db)
    ensure_retrieval_steps_column(db)
    session = ChatSession(title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: Session, limit: int = 50, offset: int = 0) -> List[ChatSession]:
    """分页查询聊天会话列表，按更新时间降序排列。

    参数:
        db: 数据库会话。
        limit: 每页数量上限，默认 50。
        offset: 偏移量，默认 0。

    返回:
        ChatSession 列表。
    """
    ensure_chat_sources_column(db)
    ensure_retrieval_params_column(db)
    ensure_retrieval_steps_column(db)
    return (
        db.query(ChatSession)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_session(db: Session, session_id: str) -> Optional[ChatSession]:
    """根据 ID 查询单个聊天会话。

    参数:
        db: 数据库会话。
        session_id: 会话唯一标识符。

    返回:
        ChatSession 对象，不存在时返回 None。
    """
    ensure_chat_sources_column(db)
    ensure_retrieval_params_column(db)
    ensure_retrieval_steps_column(db)
    return db.query(ChatSession).filter(ChatSession.id == session_id).first()


def get_session_or_raise(db: Session, session_id: str) -> ChatSession:
    """根据 ID 查询聊天会话，不存在时抛出异常。

    参数:
        db: 数据库会话。
        session_id: 会话唯一标识符。

    返回:
        ChatSession 对象。

    异常:
        ChatSessionNotFoundError: 会话不存在。
    """
    session = get_session(db, session_id)
    if session is None:
        raise ChatSessionNotFoundError(session_id)
    return session


def delete_session(db: Session, session_id: str) -> bool:
    """删除指定聊天会话及其关联消息（级联删除）。

    参数:
        db: 数据库会话。
        session_id: 会话唯一标识符。

    返回:
        是否成功删除（会话不存在时返回 False）。
    """
    session = get_session(db, session_id)
    if session is None:
        return False
    db.delete(session)
    db.commit()
    return True


def add_message(
    db: Session,
    session: ChatSession,
    role: str,
    content: str,
    *,
    has_image: bool = False,
    sources: Optional[List[dict[str, Any]]] = None,
    retrieval_params: Optional[dict[str, Any]] = None,
    retrieval_steps: Optional[List[dict[str, Any]]] = None,
) -> ChatMessage:
    """向会话中追加一条消息。

    参数:
        db: 数据库会话。
        session: 目标 ChatSession 对象。
        role: 消息角色，必须为 "user" 或 "assistant"。
        content: 消息文本内容。
        has_image: 消息是否包含图片。
        sources: 检索来源列表（仅 assistant 消息携带）。
        retrieval_params: 检索参数快照。
        retrieval_steps: 检索步骤详情列表。

    返回:
        新创建的 ChatMessage 对象。

    异常:
        ValueError: role 不在合法范围内。
    """
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role}")

    ensure_chat_sources_column(db)
    ensure_retrieval_params_column(db)
    ensure_retrieval_steps_column(db)
    message = ChatMessage(
        session_id=session.id,
        role=role,
        content=content,
        has_image=has_image,
        sources_json=dump_message_sources(sources),
        retrieval_params_json=dump_json_field(retrieval_params),
        retrieval_steps_json=dump_json_list(retrieval_steps),
    )
    session.updated_at = datetime.now(timezone.utc)
    db.add(message)
    db.add(session)
    db.commit()
    db.refresh(message)
    return message


def get_recent_history(db: Session, session_id: str, max_turns: int) -> List[Tuple[str, str]]:
    """获取会话的最近 N 轮对话历史。

    每轮以 (user_content, assistant_content) 元组表示，
    仅返回完整的 user-assistant 配对。

    参数:
        db: 数据库会话。
        session_id: 会话唯一标识符。
        max_turns: 最大返回轮数，<=0 表示返回全部。

    返回:
        按时间正序排列的 (用户消息, 助手回复) 元组列表。

    异常:
        ChatSessionNotFoundError: 会话不存在。
    """
    session = get_session_or_raise(db, session_id)
    messages = session.messages
    if not messages:
        return []

    user_assistant_pairs: List[Tuple[str, str]] = []
    pending_user: Optional[str] = None
    for message in messages:
        if message.role == "user":
            pending_user = message.content
            continue
        if message.role == "assistant" and pending_user is not None:
            user_assistant_pairs.append((pending_user, message.content))
            pending_user = None

    if max_turns <= 0:
        return user_assistant_pairs
    return user_assistant_pairs[-max_turns:]
