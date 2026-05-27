"""文件仓储层：提供 KnowledgeFile（知识库文件）和 DocumentChunk（文档分段）的数据库增删改查操作。"""

from typing import Iterable, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from core.logger import logger
from models.entities import DocumentChunk, KnowledgeFile


class FileRepo:
    """KnowledgeFile 和 DocumentChunk 持久化操作。"""

    def __init__(self, db: Session):
        self.db = db

    # ── KnowledgeFile 创建 ────────────────────────────────────────────

    def create_file(self, file: KnowledgeFile) -> KnowledgeFile:
        self.db.add(file)
        self.db.commit()
        self.db.refresh(file)
        return file

    # ── KnowledgeFile 查询 ────────────────────────────────────────────

    def get_file_by_id(self, file_id: int) -> Optional[KnowledgeFile]:
        stmt = select(KnowledgeFile).where(
            KnowledgeFile.id == file_id,
        )
        return self.db.scalars(stmt).first()

    def get_files_by_kb(self, kb_id: int) -> list[KnowledgeFile]:
        stmt = (
            select(KnowledgeFile)
            .where(KnowledgeFile.kb_id == kb_id)
            .order_by(KnowledgeFile.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_files_by_kb_paginated(
        self, kb_id: int, page: int, page_size: int
    ) -> tuple[list[KnowledgeFile], int]:
        base_stmt = select(KnowledgeFile).where(
            KnowledgeFile.kb_id == kb_id,
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

    def check_file_exists_by_md5(self, kb_id: int, md5: str) -> bool:
        stmt = select(KnowledgeFile.id).where(
            KnowledgeFile.kb_id == kb_id,
            KnowledgeFile.md5 == md5,
        )
        return self.db.execute(stmt).first() is not None

    # ── KnowledgeFile 更新 ────────────────────────────────────────────

    def update_file_status(self, file_id: int, status: int, error_msg: str | None = None):
        stmt = (
            update(KnowledgeFile)
            .where(KnowledgeFile.id == file_id)
            .values(status=status, error_msg=error_msg)
        )
        self.db.execute(stmt)
        self.db.commit()
        logger.debug(f"Updated file status: file_id={file_id}, status={status}")

    # ── KnowledgeFile 删除 ────────────────────────────────────────────

    def delete_file(self, file_id: int) -> Optional[KnowledgeFile]:
        """硬删除单个文件及其 DocumentChunk 记录。"""
        file_entity = self.get_file_by_id(file_id)
        if not file_entity:
            return None
        stmt = delete(DocumentChunk).where(DocumentChunk.file_id == file_id)
        self.db.execute(stmt)
        self.db.delete(file_entity)
        self.db.commit()
        logger.info(f"Hard deleted file and purged chunks: file_id={file_id}")
        return file_entity

    # ── DocumentChunk 操作 ────────────────────────────────────────────

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

    def delete_chunk_by_id(self, chunk_id: int, file_id: int) -> bool:
        """删除单个文档切片，返回是否成功找到并删除。"""
        chunk = self.db.get(DocumentChunk, chunk_id)
        if not chunk or chunk.file_id != file_id:
            return False
        self.db.delete(chunk)
        self.db.commit()
        return True

    def get_chunks_by_ids(self, chunk_ids: Iterable[int]) -> list[DocumentChunk]:
        chunk_ids = list(chunk_ids)
        if not chunk_ids:
            return []
        stmt = select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
        return list(self.db.scalars(stmt).all())

    def get_chunks_by_file_id_paginated(
        self, file_id: int, page: int, page_size: int
    ) -> tuple[list[DocumentChunk], int]:
        """分页获取某文件的所有分段，按 chunk_index 升序。"""
        base_stmt = select(DocumentChunk).where(DocumentChunk.file_id == file_id)
        total_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = int(self.db.scalar(total_stmt) or 0)
        stmt = (
            base_stmt
            .order_by(DocumentChunk.chunk_index.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(stmt).all()), total

    # BM25 关键词搜索（当前版本）：基于 MySQL LIKE 实现，性能有限。
    # 迁移计划：引入 Elasticsearch 后，将此方法替换为 ES 全文搜索：
    #   1. 文件解析完成后，将 DocumentChunk 同步写入 ES 索引（kb_id 分片）
    #   2. search_chunks_by_keyword 改为调用 ES client.search()，返回 chunk_id 列表
    #   3. 再通过 get_chunks_by_ids() 批量查询完整实体返回上层
    #   4. 迁移完成后可删除下方 MySQL LIKE 实现及 _escape_like 方法
    @staticmethod
    def _escape_like(keyword: str) -> str:
        """Escape special LIKE characters to prevent injection."""
        return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def search_chunks_by_keyword(self, kb_id: int, keyword: str, limit: int = 20) -> list[DocumentChunk]:
        """基于 MySQL LIKE 的关键词搜索，用于 BM25 混合检索的文本召回。"""
        if not keyword.strip():
            return []
        escaped = self._escape_like(keyword)
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.kb_id == kb_id,
                DocumentChunk.content.like(f"%{escaped}%"),
            )
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def search_chunks_by_keyword_across_kbs(self, keyword: str, limit: int = 20) -> list[DocumentChunk]:
        """跨知识库的关键词搜索。"""
        if not keyword.strip():
            return []
        escaped = self._escape_like(keyword)
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.content.like(f"%{escaped}%"))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_chunks_by_kb_id(self, kb_id: int) -> list[DocumentChunk]:
        """获取知识库下所有分段（用于 BM25 索引构建）。"""
        stmt = select(DocumentChunk).where(DocumentChunk.kb_id == kb_id)
        return list(self.db.scalars(stmt).all())
