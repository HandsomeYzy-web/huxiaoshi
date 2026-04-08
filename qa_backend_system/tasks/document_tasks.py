import traceback

from core.database import SessionLocal
from core.logger import logger
from repositories.file_repo import FileRepo
from repositories.kb_repo import KBRepo
from repositories.milvus_repo import milvus_repo
from services.rag_service import rag_service
from tasks.celery_app import celery_app


@celery_app.task(bind=True, name="process_document_task", max_retries=3)
def process_document_task(self, file_id: int):
    db = SessionLocal()
    repo = FileRepo(db)
    kb_repo = KBRepo(db)

    try:
        file_entity = repo.get_file_by_id(file_id)
        if not file_entity:
            logger.error(f"File not found, abort task: file_id={file_id}")
            repo.update_file_status(file_id, status=3, error_msg="文件记录不存在")
            return

        kb_entity = kb_repo.get_kb_by_id(file_entity.kb_id)
        if not kb_entity:
            logger.error(f"Knowledge base not found, abort task: kb_id={file_entity.kb_id}")
            repo.update_file_status(file_id, status=3, error_msg="关联的知识库不存在或已被删除")
            return

        repo.update_file_status(file_id, status=1)
        rag_service.process_and_embed_file(db, file_entity, kb_entity)
        repo.update_file_status(file_id, status=2)
        logger.info(f"Document process task completed: file_id={file_id}")
    except Exception as exc:
        logger.error(f"Document process task failed: file_id={file_id}\n{traceback.format_exc()}")
        repo.update_file_status(file_id, status=3, error_msg=str(exc)[:1000])
    finally:
        db.close()


@celery_app.task(bind=True, name="reprocess_document_task")
def reprocess_document_task(self, file_id: int):
    db = SessionLocal()
    repo = FileRepo(db)
    kb_repo = KBRepo(db)

    try:
        file_entity = repo.get_file_by_id(file_id)
        if not file_entity:
            return

        kb_entity = kb_repo.get_kb_by_id(file_entity.kb_id)
        if not kb_entity:
            logger.error(f"Knowledge base not found, abort reprocess task: kb_id={file_entity.kb_id}")
            repo.update_file_status(file_id, status=3, error_msg="关联的知识库不存在或已被删除")
            return

        repo.update_file_status(file_id, status=1)

        repo.delete_chunks_by_file_id(file_id)
        milvus_repo.delete_chunks_by_file_id(file_id)

        rag_service.process_and_embed_file(db, file_entity, kb_entity)
        repo.update_file_status(file_id, status=2)
        logger.info(f"Document reprocess task completed: file_id={file_id}")
    except Exception as exc:
        logger.error(f"Document reprocess task failed: file_id={file_id}\n{traceback.format_exc()}")
        repo.update_file_status(file_id, status=3, error_msg=str(exc)[:1000])
    finally:
        db.close()
