import hashlib
import os
from typing import List, Optional
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from models.entities import KnowledgeFile
from repositories.meta_repo import MetaRepo
from repositories.minio_repo import minio_repo
from core.logger import logger
from tasks.document_tasks import process_document_task

class FileService:
    """文件处理业务逻辑层"""

    async def calculate_md5(self, file: UploadFile) -> str:
        """
        计算上传文件的 MD5 哈希值
        采用分块读取的方式，防止超大文件撑爆内存
        """
        md5_hash = hashlib.md5()
        # 每次读取 8KB 块
        while chunk := await file.read(8192):
            md5_hash.update(chunk)

        # ⚠️ 非常重要：计算完 MD5 后，文件的读取游标已经到了末尾
        # 必须将游标重置回开头，否则后续上传 MinIO 时会读到空文件
        await file.seek(0)
        return md5_hash.hexdigest()

    async def batch_upload(
            self,
            db: Session,
            kb_id: int,
            files: List[UploadFile],
            custom_chunk_size: Optional[int] = None,
            custom_chunk_overlap: Optional[int] = None
    ) -> List[dict]:
        """
        处理批量文件上传
        包含：防重校验 -> 上传 MinIO -> 写入 MySQL -> (未来触发异步解析任务)
        """
        repo = MetaRepo(db)

        # 1. 校验知识库是否存在
        kb = repo.get_kb_by_id(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail=f"知识库 ID={kb_id} 不存在")

        results = []
        for file in files:
            try:
                # 2. 计算 MD5 并进行防重校验
                md5_str = await self.calculate_md5(file)
                if repo.check_file_exists_by_md5(kb_id, md5_str):
                    logger.info(f"文件已存在，跳过上传: {file.filename}")
                    results.append({
                        "filename": file.filename,
                        "status": "skipped",
                        "reason": "该文件已存在于当前知识库中"
                    })
                    continue

                # 3. 读取文件并提取基础信息
                file_bytes = await file.read()
                # 提取扩展名，例如 .pdf -> pdf
                file_ext = os.path.splitext(file.filename)[1].lower().strip('.')
                file_size = len(file_bytes)

                # 4. 上传至 MinIO (按知识库ID和MD5隔离目录)
                object_name = f"kb_{kb_id}/{md5_str}/{file.filename}"
                minio_repo.upload_file_bytes(object_name, file_bytes, file.content_type)

                # 5. 将文件元数据存入 MySQL
                new_file = KnowledgeFile(
                    kb_id=kb_id,
                    file_name=file.filename,
                    file_type=file_ext or "unknown",
                    file_size=file_size,
                    md5=md5_str,
                    minio_bucket=minio_repo.bucket_name,
                    minio_object_name=object_name,
                    status=0,  # 状态 0: 待处理
                    custom_chunk_size=custom_chunk_size,
                    custom_chunk_overlap=custom_chunk_overlap
                )
                repo.create_file(new_file)

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


# 实例化单例
file_service = FileService()