"""
聊天会话服务。
"""
import json
from datetime import datetime
from typing import Any, List, Optional, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.data.chat_models import ChatMessage, ChatSession


VALID_ROLES = {"user", "assistant"}


class ChatSessionNotFoundError(Exception):
    """会话不存在。"""


def ensure_chat_sources_column(db: Session) -> None:
    inspector = inspect(db.bind)
    columns = {column["name"] for column in inspector.get_columns("chat_messages")}
    if "sources_json" in columns:
        return
    db.execute(text("ALTER TABLE chat_messages ADD COLUMN sources_json TEXT"))
    db.commit()


def dump_message_sources(sources: Optional[List[dict[str, Any]]]) -> Optional[str]:
    if sources is None:
        return None
    if not sources:
        return "[]"
    return json.dumps(sources, ensure_ascii=False)


def load_message_sources(sources_json: Optional[str]) -> List[dict[str, Any]]:
    if not sources_json:
        return []
    try:
        loaded = json.loads(sources_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def create_session(db: Session, title: Optional[str] = None) -> ChatSession:
    ensure_chat_sources_column(db)
    session = ChatSession(title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: Session, limit: int = 50, offset: int = 0) -> List[ChatSession]:
    ensure_chat_sources_column(db)
    return (
        db.query(ChatSession)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_session(db: Session, session_id: str) -> Optional[ChatSession]:
    ensure_chat_sources_column(db)
    return db.query(ChatSession).filter(ChatSession.id == session_id).first()


def get_session_or_raise(db: Session, session_id: str) -> ChatSession:
    session = get_session(db, session_id)
    if session is None:
        raise ChatSessionNotFoundError(session_id)
    return session


def delete_session(db: Session, session_id: str) -> bool:
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
) -> ChatMessage:
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role}")

    ensure_chat_sources_column(db)
    message = ChatMessage(
        session_id=session.id,
        role=role,
        content=content,
        has_image=has_image,
        sources_json=dump_message_sources(sources),
    )
    session.updated_at = datetime.utcnow()
    db.add(message)
    db.add(session)
    db.commit()
    db.refresh(message)
    return message


def get_recent_history(db: Session, session_id: str, max_turns: int) -> List[Tuple[str, str]]:
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
