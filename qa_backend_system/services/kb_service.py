from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.exceptions import (
    BusinessError,
    DuplicateResourceError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from core.logger import logger
from models.entities import KnowledgeBase
from models.schemas.kb_schema import KBCreate, KBUpdate
from repositories.kb_repo import KBRepo
from repositories.milvus_repo import milvus_repo
from repositories.minio_repo import minio_repo


class KBService:
    """知识库业务逻辑处理层"""

    def _get_role_service(self):
        from services.role_service import role_service
        return role_service

    def create_kb(self, db: Session, kb_in: KBCreate, user_id: int) -> KnowledgeBase:
        repo = KBRepo(db)

        kb_entity = KnowledgeBase(
            user_id=user_id,
            name=kb_in.name,
            description=kb_in.description,
            default_chunk_size=kb_in.default_chunk_size,
            default_chunk_overlap=kb_in.default_chunk_overlap,
            retrieval_top_k=kb_in.retrieval_top_k,
            retrieval_score_threshold=kb_in.retrieval_score_threshold,
            enable_rerank=kb_in.enable_rerank,
        )

        try:
            created_kb = repo.create_kb(kb_entity)
            return created_kb
        except IntegrityError as e:
            db.rollback()
            logger.warning(f"创建知识库失败，名称已存在: {kb_in.name}")
            raise DuplicateResourceError("该知识库名称已存在，请换一个名称") from e
        except Exception as e:
            db.rollback()
            logger.error(f"创建知识库时发生未知错误: {e}")
            raise BusinessError("服务器内部错误，请联系管理员") from e

    def list_kbs(self, db: Session, user_id: int) -> list[KnowledgeBase]:
        """
        返回用户可访问的知识库列表：
        - 管理员：全部知识库
        - 普通用户：通过 KBRoleAccess 配置可访问的知识库
        """
        accessible_kb_ids = self._get_role_service().get_accessible_kb_ids(db, user_id)
        kb_repo = KBRepo(db)
        if accessible_kb_ids is None:
            # 管理员，不做 ID 过滤
            return kb_repo.get_all_kbs()
        if not accessible_kb_ids:
            return []
        return kb_repo.get_kbs_by_ids(accessible_kb_ids)

    def update_kb(self, db: Session, kb_id: int, kb_update: KBUpdate, user_id: int) -> KnowledgeBase:
        """仅创建者或管理员可更新"""
        repo = KBRepo(db)
        from repositories.user_repo import UserRepo
        user = UserRepo(db).get_by_id(user_id)
        is_admin = user and user.is_admin

        kb = repo.get_kb_by_id(kb_id)
        if not kb:
            raise ResourceNotFoundError(f"知识库 ID={kb_id} 不存在")
        if not is_admin and kb.user_id != user_id:
            raise PermissionDeniedError("只有知识库创建者或管理员可以修改知识库")
        update_data = kb_update.model_dump(exclude_unset=True)
        updated = repo.update_kb(kb_id, update_data)
        if updated is None:
            raise ResourceNotFoundError(f"知识库 ID={kb_id} 更新失败")
        logger.info(f"知识库更新: ID={kb_id}, fields={list(update_data.keys())}")
        return updated

    def delete_kb(self, db: Session, kb_id: int, user_id: int) -> None:
        """
        完整删除知识库（仅创建者或管理员可操作）：
        1. 删除 Milvus 中该知识库所有向量
        2. 删除 MinIO 中该知识库目录下所有文件
        3. 软删除 MySQL 中 KnowledgeBase / KnowledgeFile / DocumentChunk 记录
        """
        repo = KBRepo(db)
        from repositories.user_repo import UserRepo
        user = UserRepo(db).get_by_id(user_id)
        is_admin = user and user.is_admin

        kb = repo.get_kb_by_id(kb_id)
        if not kb:
            raise ResourceNotFoundError(f"知识库 ID={kb_id} 不存在或已被删除")
        if not is_admin and kb.user_id != user_id:
            raise PermissionDeniedError("只有知识库创建者或管理员可以删除知识库")

        # 按外部→内部顺序删除，失败时记录日志但继续清理
        milvus_error = None
        minio_error = None
        try:
            milvus_repo.delete_chunks_by_kb_id(kb_id)
        except Exception as e:
            milvus_error = e
            logger.error(f"删除Milvus向量失败(kb_id={kb_id}): {e}")

        try:
            minio_repo.delete_files_with_prefix(f"kb_{kb_id}/")
        except Exception as e:
            minio_error = e
            logger.error(f"删除MinIO文件失败(kb_id={kb_id}): {e}")

        # MySQL 软删除始终执行
        repo.delete_kb(kb_id)
        logger.info(f"知识库删除完成: ID={kb_id}, name={kb.name}")

        # 如果外部服务有失败，发出警告但不阻断（数据已标记删除）
        if milvus_error or minio_error:
            logger.warning(
                f"知识库 ID={kb_id} 已软删除，但部分外部资源清理失败: "
                f"milvus={'OK' if not milvus_error else str(milvus_error)}, "
                f"minio={'OK' if not minio_error else str(minio_error)}"
            )


# 实例化单例供 Router 调用
kb_service = KBService()
