from sqlalchemy.orm import Session
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from models.schemas.kb_schema import KBCreate
from models.entities import KnowledgeBase
from repositories.meta_repo import MetaRepo
from core.logger import logger


class KBService:
    """知识库业务逻辑处理层"""

    def create_kb(self, db: Session, kb_in: KBCreate) -> KnowledgeBase:
        repo = MetaRepo(db)

        # 1. 将 Pydantic Schema 转换为 SQLAlchemy Entity
        kb_entity = KnowledgeBase(
            name=kb_in.name,
            description=kb_in.description,
            default_chunk_size=kb_in.default_chunk_size,
            default_chunk_overlap=kb_in.default_chunk_overlap
        )

        # 2. 调用数据访问层保存到数据库，并捕获唯一索引冲突
        try:
            created_kb = repo.create_kb(kb_entity)
            return created_kb
        except IntegrityError:
            db.rollback()  # 发生异常时必须回滚事务
            logger.warning(f"创建知识库失败，名称已存在: {kb_in.name}")
            raise HTTPException(status_code=400, detail="该知识库名称已存在，请换一个名称")
        except Exception as e:
            db.rollback()
            logger.error(f"创建知识库时发生未知错误: {e}")
            raise HTTPException(status_code=500, detail="服务器内部错误，请联系管理员")


# 实例化单例供 Router 调用
kb_service = KBService()