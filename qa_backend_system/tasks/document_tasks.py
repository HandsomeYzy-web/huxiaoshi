import traceback

from tasks.celery_app import celery_app
from core.database import SessionLocal
from core.logger import logger
from repositories.meta_repo import MetaRepo
from repositories.milvus_repo import milvus_repo
from services.rag_service import rag_service


@celery_app.task(bind=True, name="process_document_task", max_retries=3)
def process_document_task(self, file_id: int):
    db = SessionLocal()
    repo = MetaRepo(db)

    try:
        file_entity = repo.get_file_by_id(file_id)
        if not file_entity:
            logger.error(f"File not found, abort task: file_id={file_id}")
            return

        kb_entity = repo.get_kb_by_id(file_entity.kb_id)
        if not kb_entity:
            logger.error(f"Knowledge base not found, abort task: kb_id={file_entity.kb_id}")
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
    repo = MetaRepo(db)

    try:
        file_entity = repo.get_file_by_id(file_id)
        if not file_entity:
            return

        kb_entity = repo.get_kb_by_id(file_entity.kb_id)
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
