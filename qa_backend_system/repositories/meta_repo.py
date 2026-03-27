from typing import Iterable, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from core.logger import logger
from models.entities import DocumentChunk, KnowledgeBase, KnowledgeFile


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
