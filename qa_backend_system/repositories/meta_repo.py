from typing import Iterable, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from core.logger import logger
from models.entities import ChatMessage, ChatSession, DocumentChunk, KnowledgeBase, KnowledgeFile


class MetaRepo:
    """Metadata persistence in MySQL."""

    def __init__(self, db: Session):
        self.db = db

    def create_kb(self, kb: KnowledgeBase) -> KnowledgeBase:
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        logger.info(f"Created knowledge base: {kb.name} (ID: {kb.id})")
        return kb

    def get_kb_by_id(self, kb_id: int) -> Optional[KnowledgeBase]:
        stmt = select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.is_deleted.is_(False))
        return self.db.scalars(stmt).first()

    def get_all_kbs(self) -> list[KnowledgeBase]:
        stmt = (
            select(KnowledgeBase)
            .where(KnowledgeBase.is_deleted.is_(False))
            .order_by(KnowledgeBase.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_kbs_by_ids(self, kb_ids: Iterable[int]) -> list[KnowledgeBase]:
        kb_ids = list(kb_ids)
        if not kb_ids:
            return []
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.id.in_(kb_ids),
            KnowledgeBase.is_deleted.is_(False),
        )
        return list(self.db.scalars(stmt).all())

    def delete_kb(self, kb_id: int) -> bool:
        kb = self.get_kb_by_id(kb_id)
        if not kb:
            return False
        kb.is_deleted = True
        for file in kb.files:
            file.is_deleted = True
        self.db.commit()
        logger.info(f"Soft deleted knowledge base: ID={kb_id}")
        return True

    def create_file(self, file: KnowledgeFile) -> KnowledgeFile:
        self.db.add(file)
        self.db.commit()
        self.db.refresh(file)
        return file

    def check_file_exists_by_md5(self, kb_id: int, md5: str) -> bool:
        stmt = select(KnowledgeFile.id).where(
            KnowledgeFile.kb_id == kb_id,
            KnowledgeFile.md5 == md5,
            KnowledgeFile.is_deleted.is_(False),
        )
        return self.db.execute(stmt).first() is not None

    def get_files_by_kb(self, kb_id: int) -> list[KnowledgeFile]:
        stmt = (
            select(KnowledgeFile)
            .where(KnowledgeFile.kb_id == kb_id, KnowledgeFile.is_deleted.is_(False))
            .order_by(KnowledgeFile.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_files_by_kb_paginated(self, kb_id: int, page: int, page_size: int) -> tuple[list[KnowledgeFile], int]:
        base_stmt = select(KnowledgeFile).where(
            KnowledgeFile.kb_id == kb_id,
            KnowledgeFile.is_deleted.is_(False),
        )
        total_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = int(self.db.scalar(total_stmt) or 0)

        stmt = (
            base_stmt
            .order_by(KnowledgeFile.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(stmt).all()), total

    def get_files_by_ids(self, file_ids: Iterable[int]) -> list[KnowledgeFile]:
        file_ids = list(file_ids)
        if not file_ids:
            return []
        stmt = select(KnowledgeFile).where(KnowledgeFile.id.in_(file_ids))
        return list(self.db.scalars(stmt).all())

    def update_file_status(self, file_id: int, status: int, error_msg: str | None = None):
        stmt = update(KnowledgeFile).where(KnowledgeFile.id == file_id).values(status=status, error_msg=error_msg)
        self.db.execute(stmt)
        self.db.commit()
        logger.debug(f"Updated file status: file_id={file_id}, status={status}")

    def get_file_by_id(self, file_id: int) -> Optional[KnowledgeFile]:
        stmt = select(KnowledgeFile).where(KnowledgeFile.id == file_id, KnowledgeFile.is_deleted.is_(False))
        return self.db.scalars(stmt).first()

    def bulk_create_chunks(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        self.db.add_all(chunks)
        self.db.commit()
        for chunk in chunks:
            self.db.refresh(chunk)
        return chunks

    def delete_chunks_by_file_id(self, file_id: int):
        stmt = delete(DocumentChunk).where(DocumentChunk.file_id == file_id)
        self.db.execute(stmt)
        self.db.commit()

    def get_chunks_by_ids(self, chunk_ids: Iterable[int]) -> list[DocumentChunk]:
        chunk_ids = list(chunk_ids)
        if not chunk_ids:
            return []
        stmt = select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
        return list(self.db.scalars(stmt).all())

    def create_chat_session(self, session: ChatSession) -> ChatSession:
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def list_chat_sessions(self, user_id: int) -> list[ChatSession]:
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id, ChatSession.is_deleted.is_(False))
            .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_chat_session(self, session_id: int, user_id: int) -> Optional[ChatSession]:
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
            ChatSession.is_deleted.is_(False),
        )
        return self.db.scalars(stmt).first()

    def update_chat_session_title(self, session_id: int, title: str):
        stmt = update(ChatSession).where(ChatSession.id == session_id).values(title=title)
        self.db.execute(stmt)
        self.db.commit()

    def touch_chat_session(self, session_id: int):
        stmt = update(ChatSession).where(ChatSession.id == session_id).values(updated_at=func.now())
        self.db.execute(stmt)
        self.db.commit()

    def create_chat_message(self, message: ChatMessage) -> ChatMessage:
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def list_chat_messages(self, session_id: int) -> list[ChatMessage]:
        stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
        return list(self.db.scalars(stmt).all())
