import traceback
from celery import shared_task

from tasks.celery_app import celery_app
from core.database import SessionLocal
from core.logger import logger
from repositories.meta_repo import MetaRepo
from repositories.milvus_repo import milvus_repo
from services.rag_service import rag_service


@celery_app.task(bind=True, name="process_document_task", max_retries=3)
def process_document_task(self, file_id: int):
    """
    后台任务：首次处理上传的文档
    包含状态流转：0(待处理) -> 1(解析中) -> 2(已完成) / 3(失败)
    """
    logger.info(f"📥 [后台任务启动] 准备解析文件 ID: {file_id}")

    # Celery 任务在独立的进程中运行，必须手动创建和销毁数据库会话
    db = SessionLocal()
    repo = MetaRepo(db)

    try:
        # 1. 获取文件实体和知识库实体
        file_entity = repo.get_file_by_id(file_id)
        if not file_entity:
            logger.error(f"❌ 文件 ID={file_id} 不存在，任务终止。")
            return

        kb_entity = repo.get_kb_by_id(file_entity.kb_id)
        if not kb_entity:
            logger.error(f"❌ 关联的知识库 ID={file_entity.kb_id} 不存在，任务终止。")
            return

        # 2. 更新状态为 1 (解析中)
        repo.update_file_status(file_id, status=1)

        # 3. 调用 RAG 引擎执行极其耗时的解析与向量化工作
        rag_service.process_and_embed_file(file_entity, kb_entity)

        # 4. 如果没有抛出异常，更新状态为 2 (已完成)
        repo.update_file_status(file_id, status=2)
        logger.info(f"✅ [后台任务完成] 文件 ID: {file_id} 解析并入库成功！")

    except Exception as exc:
        # 记录详细的崩溃堆栈
        error_details = traceback.format_exc()
        logger.error(f"❌ [后台任务失败] 文件 ID: {file_id} 解析报错:\n{error_details}")

        # 更新状态为 3 (失败)，并截取前 1000 个字符的错误信息存入数据库供前端查看
        repo.update_file_status(file_id, status=3, error_msg=str(exc)[:1000])

        # 如果是偶发的网络或 API 错误，可以选择重试
        # raise self.retry(exc=exc, countdown=60) # 60秒后重试

    finally:
        # 无论成功失败，必须释放数据库连接
        db.close()


@celery_app.task(bind=True, name="reprocess_document_task")
def reprocess_document_task(self, file_id: int):
    """
    后台任务：当用户单独修改了某一个文件的切分策略后，触发重新解析
    """
    logger.info(f"🔄 [后台重算任务启动] 准备重新解析文件 ID: {file_id}")

    db = SessionLocal()
    repo = MetaRepo(db)

    try:
        file_entity = repo.get_file_by_id(file_id)
        if not file_entity:
            return

        kb_entity = repo.get_kb_by_id(file_entity.kb_id)

        # 1. 更新状态为 1 (解析中)
        repo.update_file_status(file_id, status=1)

        # 2. 核心差异：必须先清理 Milvus 中该文件旧的 Chunk 向量数据
        logger.info(f"🧹 正在清理文件 ID={file_id} 的旧向量数据...")
        milvus_repo.delete_chunks_by_file_id(file_id)

        # 3. 重新调用 RAG 引擎解析并生成新的 Chunk
        rag_service.process_and_embed_file(file_entity, kb_entity)

        # 4. 更新状态为 2 (已完成)
        repo.update_file_status(file_id, status=2)
        logger.info(f"✅ [后台重算任务完成] 文件 ID: {file_id} 按新策略重新入库成功！")

    except Exception as exc:
        error_details = traceback.format_exc()
        logger.error(f"❌ [后台重算任务失败] 文件 ID: {file_id}:\n{error_details}")
        repo.update_file_status(file_id, status=3, error_msg=str(exc)[:1000])
    finally:
        db.close()