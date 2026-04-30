import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.exceptions import BusinessError, DuplicateResourceError, PermissionDeniedError, ResourceNotFoundError
from core.logger import logger
from models.entities import KnowledgeBase
from models.schemas.kb_schema import KBCreate, KBUpdate
from repositories.kb_repo import KBRepo
from repositories.milvus_repo import milvus_repo
from repositories.minio_repo import minio_repo
from services.kb_access_service import kb_access_service


class KBService:
    def create_kb(self, db: Session, kb_in: KBCreate, user_id: int) -> KnowledgeBase:
        repo = KBRepo(db)

        kb_entity = KnowledgeBase(
            user_id=user_id,
            name=kb_in.name,
            description=kb_in.description,
            default_chunk_size=kb_in.default_chunk_size,
            default_chunk_overlap=kb_in.default_chunk_overlap,
            default_separators=json.dumps(kb_in.default_separators, ensure_ascii=False)
            if kb_in.default_separators
            else None,
            retrieval_top_k=kb_in.retrieval_top_k,
            retrieval_score_threshold=kb_in.retrieval_score_threshold,
            enable_rerank=kb_in.enable_rerank,
        )

        try:
            created_kb = repo.create_kb(kb_entity)
            milvus_repo.ensure_collection(created_kb.id)
            return created_kb
        except IntegrityError:
            db.rollback()
            logger.warning(f"Failed to create knowledge base, duplicate name: {kb_in.name}")
            raise DuplicateResourceError("Knowledge base name already exists")
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to create knowledge base: {exc}")
            raise BusinessError("Server internal error")

    def list_kbs(self, db: Session, user_id: int) -> list[KnowledgeBase]:
        # TODO: 后续改为通过角色权限控制访问，用户只能通过角色获得访问权限，不再区分拥有和被授权的知识库
        accessible_kb_ids = kb_access_service.get_accessible_kb_ids(db, user_id)
        kb_repo = KBRepo(db)
        if not accessible_kb_ids:
            return []
        return kb_repo.get_kbs_by_ids(accessible_kb_ids)

    def update_kb(self, db: Session, kb_id: int, kb_update: KBUpdate, user_id: int) -> KnowledgeBase:
        repo = KBRepo(db)
        kb = repo.get_kb_by_id(kb_id)
        if not kb:
            raise ResourceNotFoundError(f"知识库 ID={kb_id} 不存在")
        # TODO: 后续改为通过角色权限控制访问，用户只能通过角色获得访问权限，不再区分拥有和被授权的知识库
        if kb.user_id != user_id:
            raise PermissionDeniedError("只有知识库创建者可以修改知识库")
        update_data = kb_update.model_dump(exclude_unset=True)
        updated = repo.update_kb(kb_id, update_data)
        logger.info(f"知识库更新: ID={kb_id}, fields={list(update_data.keys())}")
        return updated

    # TODO: 这里应该先检查吗，milvus和minio的删除标记，如果有报错则不继续删除，而是将失败存入数据库，给出错误提示方便下一次继续删除（即重试删除），这个更改可能会涉及数据库的字段增加
    def delete_kb(self, db: Session, kb_id: int, user_id: int) -> None:
        repo = KBRepo(db)
        kb = repo.get_kb_by_id(kb_id)
        if not kb:
            raise ResourceNotFoundError(f"知识库 ID={kb_id} 不存在或已被删除")
        # TODO: 后续改为通过角色权限控制访问，用户只能通过角色获得访问权限，不再区分拥有和被授权的知识库
        if kb.user_id != user_id:
            raise PermissionDeniedError("只有知识库创建者可以删除知识库")

        milvus_error = None
        minio_error = None
        try:
            milvus_repo.delete_chunks_by_kb_id(kb_id)
        except Exception as exc:
            milvus_error = exc
            logger.error(f"删除 Milvus 向量失败(kb_id={kb_id}): {exc}")

        try:
            minio_repo.delete_files_with_prefix(f"kb_{kb_id}/")
        except Exception as exc:
            minio_error = exc
            logger.error(f"删除 MinIO 文件失败(kb_id={kb_id}): {exc}")

        repo.delete_kb(kb_id)
        logger.info(f"知识库删除完成: ID={kb_id}, name={kb.name}")

        if milvus_error or minio_error:
            logger.warning(
                "知识库已硬删除，但部分外部资源清理失败: "
                f"milvus={'OK' if not milvus_error else str(milvus_error)}, "
                f"minio={'OK' if not minio_error else str(minio_error)}"
            )


kb_service = KBService()
