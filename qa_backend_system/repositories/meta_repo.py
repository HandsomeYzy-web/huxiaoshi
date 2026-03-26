from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from models.entities import KnowledgeBase, KnowledgeFile
from core.logger import logger

class MetaRepo:
    """元数据库 (MySQL) 访问层封装"""

    def __init__(self, db: Session):
        self.db = db

    # ==========================================
    # 知识库 (KnowledgeBase) 操作
    # ==========================================
    def create_kb(self, kb: KnowledgeBase) -> KnowledgeBase:
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        logger.info(f"创建知识库成功: {kb.name} (ID: {kb.id})")
        return kb

    def get_kb_by_id(self, kb_id: int) -> Optional[KnowledgeBase]:
        stmt = select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.is_deleted == False)
        return self.db.scalars(stmt).first()

    def get_all_kbs(self) -> List[KnowledgeBase]:
        stmt = select(KnowledgeBase).where(KnowledgeBase.is_deleted == False).order_by(KnowledgeBase.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def delete_kb(self, kb_id: int) -> bool:
        """软删除知识库及关联文件"""
        kb = self.get_kb_by_id(kb_id)
        if not kb:
            return False
        kb.is_deleted = True
        # 级联软删除文件
        for file in kb.files:
            file.is_deleted = True
        self.db.commit()
        logger.info(f"软删除知识库成功: ID={kb_id}")
        return True

    # ==========================================
    # 知识库文件 (KnowledgeFile) 操作
    # ==========================================
    def create_file(self, file: KnowledgeFile) -> KnowledgeFile:
        self.db.add(file)
        self.db.commit()
        self.db.refresh(file)
        return file

    def check_file_exists_by_md5(self, kb_id: int, md5: str) -> bool:
        """防重复上传校验：检查同知识库下是否已存在该 MD5 的文件"""
        stmt = select(KnowledgeFile.id).where(
            KnowledgeFile.kb_id == kb_id,
            KnowledgeFile.md5 == md5,
            KnowledgeFile.is_deleted == False
        )
        return self.db.execute(stmt).first() is not None

    def get_files_by_kb(self, kb_id: int) -> List[KnowledgeFile]:
        stmt = select(KnowledgeFile).where(
            KnowledgeFile.kb_id == kb_id,
            KnowledgeFile.is_deleted == False
        ).order_by(KnowledgeFile.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def update_file_status(self, file_id: int, status: int, error_msg: str = None):
        stmt = update(KnowledgeFile).where(KnowledgeFile.id == file_id).values(status=status, error_msg=error_msg)
        self.db.execute(stmt)
        self.db.commit()
        logger.debug(f"更新文件 ID={file_id} 状态为 {status}")

    def get_file_by_id(self, file_id: int) -> Optional[KnowledgeFile]:
        stmt = select(KnowledgeFile).where(KnowledgeFile.id == file_id, KnowledgeFile.is_deleted == False)
        return self.db.scalars(stmt).first()