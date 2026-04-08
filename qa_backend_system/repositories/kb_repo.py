from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.logger import logger
from models.entities import DocumentChunk, KnowledgeBase


class KBRepo:
    """知识库（KnowledgeBase）持久化操作。"""

    def __init__(self, db: Session):
        self.db = db

    # ── 创建 ─────────────────────────────────────────────────────────

    def create_kb(self, kb: KnowledgeBase) -> KnowledgeBase:
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        logger.info(f"Created knowledge base: {kb.name} (ID: {kb.id})")
        return kb

    # ── 查询 ─────────────────────────────────────────────────────────

    def get_kb_by_id(self, kb_id: int, user_id: int | None = None) -> KnowledgeBase | None:
        """按 ID 查询知识库；传入 user_id 时额外校验归属。"""
        conditions = [KnowledgeBase.id == kb_id, KnowledgeBase.is_deleted.is_(False)]
        if user_id is not None:
            conditions.append(KnowledgeBase.user_id == user_id)
        stmt = select(KnowledgeBase).where(*conditions)
        return self.db.scalars(stmt).first()

    def get_all_kbs(self, user_id: int | None = None) -> list[KnowledgeBase]:
        """查询知识库列表；传入 user_id 时过滤归属，否则返回全部（跨用户场景）。"""
        conditions = [KnowledgeBase.is_deleted.is_(False)]
        if user_id is not None:
            conditions.append(KnowledgeBase.user_id == user_id)
        stmt = (
            select(KnowledgeBase)
            .where(*conditions)
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

    # ── 更新 ─────────────────────────────────────────────────────────

    def update_kb(self, kb_id: int, update_data: dict) -> KnowledgeBase | None:
        """按字段字典更新知识库，返回更新后的实体。"""
        kb = self.get_kb_by_id(kb_id)
        if not kb:
            return None
        for field, value in update_data.items():
            if hasattr(kb, field) and value is not None:
                setattr(kb, field, value)
        self.db.commit()
        self.db.refresh(kb)
        return kb

    # ── 删除 ─────────────────────────────────────────────────────────

    def delete_kb(self, kb_id: int) -> bool:
        """软删除知识库及其所有文件，并硬删除关联的 DocumentChunk 记录。"""
        kb = self.get_kb_by_id(kb_id)
        if not kb:
            return False
        kb.is_deleted = True
        for file in kb.files:
            file.is_deleted = True
        stmt = delete(DocumentChunk).where(DocumentChunk.kb_id == kb_id)
        self.db.execute(stmt)
        self.db.commit()
        logger.info(f"Soft deleted knowledge base and purged chunks: ID={kb_id}")
        return True
