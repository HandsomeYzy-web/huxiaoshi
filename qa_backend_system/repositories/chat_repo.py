"""聊天仓储层：提供 ChatSession（聊天会话）和 ChatMessage（聊天消息）的数据库增删改查操作。"""

from typing import Optional

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from core.logger import logger
from models.entities import ChatMessage, ChatSession


class ChatRepo:
    """ChatSession 和 ChatMessage 持久化操作。"""

    def __init__(self, db: Session):
        self.db = db

    # ── ChatSession 创建 ──────────────────────────────────────────────

    def create_chat_session(self, session: ChatSession) -> ChatSession:
        self.db.add(session)
        try:
            self.db.commit()
            self.db.refresh(session)
            return session
        except OperationalError as exc:
            self.db.rollback()
            error_text = str(exc)
            if "Field 'is_deleted' doesn't have a default value" not in error_text:
                raise

            # Compatibility fallback for legacy schemas where chat_session.is_deleted
            # exists but has no default value configured.
            insert_stmt = text(
                "INSERT INTO chat_session (user_id, title, is_deleted) VALUES (:user_id, :title, 0)"
            )
            result = self.db.execute(
                insert_stmt,
                {
                    "user_id": int(session.user_id),
                    "title": str(session.title),
                },
            )
            self.db.commit()

            inserted_id = int(result.lastrowid or 0)
            recovered = self.db.get(ChatSession, inserted_id) if inserted_id > 0 else None
            if recovered is None:
                raise RuntimeError("创建聊天会话失败：无法读取新建会话记录") from exc
            return recovered

    # ── ChatSession 查询 ──────────────────────────────────────────────

    def list_chat_sessions(self, user_id: int) -> list[ChatSession]:
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_chat_session(self, session_id: int, user_id: int) -> Optional[ChatSession]:
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        return self.db.scalars(stmt).first()

    # ── ChatSession 更新 ──────────────────────────────────────────────

    def update_chat_session_title(self, session_id: int, title: str):
        stmt = update(ChatSession).where(ChatSession.id == session_id).values(title=title)
        self.db.execute(stmt)
        self.db.commit()

    def touch_chat_session(self, session_id: int):
        """更新会话的 updated_at 时间戳。"""
        stmt = update(ChatSession).where(ChatSession.id == session_id).values(updated_at=func.now())
        self.db.execute(stmt)
        self.db.commit()

    def rename_chat_session(self, session_id: int, user_id: int, title: str) -> Optional[ChatSession]:
        session = self.get_chat_session(session_id, user_id)
        if not session:
            return None
        session.title = title.strip()
        self.db.commit()
        self.db.refresh(session)
        return session

    # ── ChatSession 删除 ──────────────────────────────────────────────

    def delete_chat_session(self, session_id: int, user_id: int) -> bool:
        session = self.get_chat_session(session_id, user_id)
        if not session:
            return False
        self.db.delete(session)
        self.db.commit()
        logger.info(f"Hard deleted chat session: session_id={session_id}")
        return True

    # ── ChatMessage ───────────────────────────────────────────────────

    def create_chat_message(self, message: ChatMessage) -> ChatMessage:
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def list_chat_messages(self, session_id: int) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())

    def list_recent_chat_messages(self, session_id: int, limit: int) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
        messages = list(self.db.scalars(stmt).all())
        messages.reverse()
        return messages
