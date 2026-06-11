import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.exceptions import BusinessError, DuplicateResourceError, ResourceNotFoundError
from core.logger import logger
from models.entities import KnowledgeBase
from models.schemas.kb_schema import KBCreate, KBUpdate
from repositories.kb_repo import KBRepo
from repositories.elasticsearch_repo import es_repo
from repositories.minio_repo import minio_repo


class KBService:
    @staticmethod
    def _check_reserved_purpose_unique(repo: KBRepo, purpose: str, exclude_kb_id: int | None = None) -> None:
        """text2SQL 专用用途（table_desc / few_shot）全局只允许一个知识库，避免检索目标歧义。"""
        if purpose not in ("table_desc", "few_shot"):
            return
        existing = [kb for kb in repo.get_kbs_by_purpose(purpose) if kb.id != exclude_kb_id]
        if existing:
            raise DuplicateResourceError(
                f"已存在用途为「{purpose}」的知识库（{existing[0].name}），该用途只允许一个知识库"
            )

    def create_kb(self, db: Session, kb_in: KBCreate, user_id: int) -> KnowledgeBase:
        repo = KBRepo(db)
        self._check_reserved_purpose_unique(repo, kb_in.purpose)

        kb_entity = KnowledgeBase(
            user_id=user_id,
            name=kb_in.name,
            description=kb_in.description,
            purpose=kb_in.purpose,
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
            es_repo.ensure_index(created_kb.id)
            return created_kb
        except IntegrityError:
            db.rollback()
            logger.warning(f"Failed to create knowledge base, duplicate name: {kb_in.name}")
            raise DuplicateResourceError("Knowledge base name already exists")
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to create knowledge base: {exc}")
            raise BusinessError("Server internal error")

    def list_kbs(self, db: Session) -> list[KnowledgeBase]:
        """列出全部知识库（去鉴权后所有知识库全局共享）。"""
        return KBRepo(db).get_all_kbs()

    def update_kb(self, db: Session, kb_id: int, kb_update: KBUpdate) -> KnowledgeBase:
        repo = KBRepo(db)
        kb = repo.get_kb_by_id(kb_id)
        if not kb:
            raise ResourceNotFoundError(f"知识库 ID={kb_id} 不存在")
        update_data = kb_update.model_dump(exclude_unset=True)
        if update_data.get("purpose"):
            self._check_reserved_purpose_unique(repo, update_data["purpose"], exclude_kb_id=kb_id)
        updated = repo.update_kb(kb_id, update_data)
        logger.info(f"知识库更新: ID={kb_id}, fields={list(update_data.keys())}")
        return updated

    def delete_kb(self, db: Session, kb_id: int) -> None:
        repo = KBRepo(db)
        kb = repo.get_kb_by_id(kb_id)
        if not kb:
            raise ResourceNotFoundError(f"知识库 ID={kb_id} 不存在或已被删除")

        es_error = None
        minio_error = None
        try:
            es_repo.delete_chunks_by_kb_id(kb_id)
        except Exception as exc:
            es_error = exc
            logger.error(f"删除 Elasticsearch 向量失败(kb_id={kb_id}): {exc}")

        try:
            minio_repo.delete_files_with_prefix(f"kb_{kb_id}/")
        except Exception as exc:
            minio_error = exc
            logger.error(f"删除 MinIO 文件失败(kb_id={kb_id}): {exc}")

        repo.delete_kb(kb_id)
        logger.info(f"知识库删除完成: ID={kb_id}, name={kb.name}")

        if es_error or minio_error:
            logger.warning(
                "知识库已硬删除，但部分外部资源清理失败: "
                f"elasticsearch={'OK' if not es_error else str(es_error)}, "
                f"minio={'OK' if not minio_error else str(minio_error)}"
            )


kb_service = KBService()
