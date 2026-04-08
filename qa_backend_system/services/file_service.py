import hashlib
import os

from fastapi import UploadFile
from sqlalchemy.orm import Session

from core.exceptions import ResourceNotFoundError
from core.logger import logger
from models.entities import KnowledgeFile
from repositories.file_repo import FileRepo
from repositories.kb_repo import KBRepo
from repositories.milvus_repo import milvus_repo
from repositories.minio_repo import minio_repo
from tasks.document_tasks import process_document_task


class FileService:
    """文件处理业务逻辑层"""

    async def calculate_md5(self, file: UploadFile) -> str:
        """
        计算上传文件的 MD5 哈希值
        采用分块读取的方式，防止超大文件撑爆内存
        """
        md5_hash = hashlib.md5(usedforsecurity=False)
        while chunk := await file.read(8192):
            md5_hash.update(chunk)
        await file.seek(0)
        return md5_hash.hexdigest()

    async def batch_upload(
            self,
            db: Session,
            kb_id: int,
            files: list[UploadFile],
            user_id: int,
            custom_chunk_size: int | None = None,
            custom_chunk_overlap: int | None = None
    ) -> list[dict]:
        """
        处理批量文件上传
        包含：防重校验 -> 上传 MinIO -> 写入 MySQL -> 触发异步解析任务
        """
        kb_repo = KBRepo(db)
        file_repo = FileRepo(db)

        kb = kb_repo.get_kb_by_id(kb_id, user_id)
        if not kb:
            raise ResourceNotFoundError(f"知识库 ID={kb_id} 不存在或无权访问")

        results = []
        for file in files:
            try:
                md5_str = await self.calculate_md5(file)
                if file_repo.check_file_exists_by_md5(kb_id, md5_str):
                    logger.info(f"文件已存在，跳过上传: {file.filename}")
                    results.append({
                        "filename": file.filename,
                        "status": "skipped",
                        "reason": "该文件已存在于当前知识库中"
                    })
                    continue

                file_bytes = await file.read()
                file_ext = os.path.splitext(file.filename)[1].lower().strip('.')
                file_size = len(file_bytes)

                object_name = f"kb_{kb_id}/{md5_str}/{file.filename}"
                minio_repo.upload_file_bytes(object_name, file_bytes, file.content_type)

                new_file = KnowledgeFile(
                    kb_id=kb_id,
                    file_name=file.filename,
                    file_type=file_ext or "unknown",
                    file_size=file_size,
                    md5=md5_str,
                    minio_bucket=minio_repo.bucket_name,
                    minio_object_name=object_name,
                    status=0,
                    custom_chunk_size=custom_chunk_size,
                    custom_chunk_overlap=custom_chunk_overlap
                )
                file_repo.create_file(new_file)

                # Bug 修复：先 commit 拿到 file_id，再触发 Celery 任务
                # 避免 Celery 在 MySQL 提交前读取到空记录
                process_document_task.delay(new_file.id)

                logger.info(f"文件上传成功: {file.filename} (ID: {new_file.id})")
                results.append({
                    "filename": file.filename,
                    "status": "success",
                    "file_id": new_file.id
                })

            except Exception as e:
                logger.error(f"处理文件 {file.filename} 时出错: {str(e)}")
                results.append({
                    "filename": file.filename,
                    "status": "failed",
                    "reason": "服务器内部处理错误"
                })

        return results

    def delete_file(self, db: Session, file_id: int, user_id: int) -> None:
        """
        完整删除单个文件：
        1. 删除 Milvus 中该文件所有向量
        2. 删除 MinIO 中该文件对象
        3. 软删除 MySQL 中 KnowledgeFile / DocumentChunk 记录
        """
        file_repo = FileRepo(db)
        file_entity = file_repo.get_file_by_id(file_id)
        if not file_entity:
            raise ResourceNotFoundError(f"文件 ID={file_id} 不存在或已被删除")
        # 校验该文件属于当前用户
        kb = KBRepo(db).get_kb_by_id(file_entity.kb_id, user_id)
        if not kb:
            raise ResourceNotFoundError(f"文件 ID={file_id} 不存在或无权访问")

        # 失败时 repo 层会抛 ExternalServiceError，由全局 handler 处理
        milvus_repo.delete_chunks_by_file_id(file_id)
        minio_repo.delete_file(file_entity.minio_object_name)

        file_repo.delete_file(file_id)
        logger.info(f"文件删除完成: file_id={file_id}, name={file_entity.file_name}")


# 实例化单例
file_service = FileService()
