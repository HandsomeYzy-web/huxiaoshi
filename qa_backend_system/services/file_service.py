"""文件服务层：处理文件批量上传（MD5 去重、存储到 MinIO、触发异步解析任务）和文件删除（级联清理 Milvus、MinIO、MySQL）。"""

import hashlib
import json
import math
import os
from typing import List, Optional
from fastapi import UploadFile
from sqlalchemy.orm import Session

from core.config import settings
from core.exceptions import ResourceNotFoundError, BusinessError
from models.entities import KnowledgeFile
from models.schemas.file_schema import ChunkPreviewRequest, FileStrategyUpdate
from repositories.kb_repo import KBRepo
from repositories.file_repo import FileRepo
from repositories.kb_access_repo import get_accessible_kb_ids
from repositories.minio_repo import minio_repo
from repositories.milvus_repo import milvus_repo
from core.logger import logger
from tasks.document_tasks import process_document_task, reprocess_document_task


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

    def _ensure_kb_access(self, db: Session, user_id: int, kb_id: int) -> None:
        """验证用户对知识库的访问权限（含自己创建 + 角色授权），优先从 Redis 缓存读取。"""
        if kb_id not in get_accessible_kb_ids(db, user_id):
            raise ResourceNotFoundError(f"知识库 ID={kb_id} 不存在或无权访问")

    async def batch_upload(
            self,
            db: Session,
            kb_id: int,
            files: List[UploadFile],
            user_id: int,
            custom_chunk_size: Optional[int] = None,
            custom_chunk_overlap: Optional[int] = None
    ) -> List[dict]:
        """
        处理批量文件上传
        包含：访问权限校验 -> 防重校验 -> 上传 MinIO -> 写入 MySQL -> 触发异步解析任务
        """
        kb_repo = KBRepo(db)
        file_repo = FileRepo(db)

        kb = kb_repo.get_kb_by_id(kb_id)
        if not kb:
            raise ResourceNotFoundError(f"知识库 ID={kb_id} 不存在")
        self._ensure_kb_access(db, user_id, kb_id)

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

    def list_kb_files(
        self, db: Session, kb_id: int, user_id: int, page: int, page_size: int
    ) -> tuple:
        """分页获取知识库文件列表。"""
        file_repo = FileRepo(db)
        items, total = file_repo.get_files_by_kb_paginated(kb_id, page, page_size)
        total_pages = math.ceil(total / page_size) if page_size else 1
        return items, total, total_pages

    def get_file_chunks(
        self, db: Session, file_id: int, user_id: int, page: int, page_size: int
    ) -> tuple:
        """分页获取文件的文档切片列表（含权限校验）。"""
        file_repo = FileRepo(db)
        file_entity = file_repo.get_file_by_id(file_id)
        if not file_entity:
            raise ResourceNotFoundError(f"文件 ID={file_id} 不存在")
        self._ensure_kb_access(db, user_id, file_entity.kb_id)
        chunks, total = file_repo.get_chunks_by_file_id_paginated(file_id, page, page_size)
        total_pages = math.ceil(total / page_size) if page_size else 1
        return chunks, total, total_pages

    def update_file_strategy(
        self, db: Session, file_id: int, strategy_in: FileStrategyUpdate, user_id: int
    ) -> KnowledgeFile:
        """更新文件切分策略并触发重新解析任务。"""
        file_repo = FileRepo(db)
        file_entity = file_repo.get_file_by_id(file_id)
        if not file_entity:
            raise ResourceNotFoundError(f"文件 ID={file_id} 不存在")
        self._ensure_kb_access(db, user_id, file_entity.kb_id)

        file_entity.custom_chunk_size = strategy_in.custom_chunk_size
        file_entity.custom_chunk_overlap = strategy_in.custom_chunk_overlap
        file_entity.custom_separators = (
            json.dumps(strategy_in.custom_separators, ensure_ascii=False)
            if strategy_in.custom_separators is not None
            else None
        )
        db.commit()
        db.refresh(file_entity)

        reprocess_document_task.delay(file_id)
        logger.info(f"切分策略已更新并触发重新解析: file_id={file_id}")
        return file_entity

    def get_image_url(
        self, db: Session, kb_id: int, image_name: str, user_id: int
    ) -> str:
        """获取知识库图片的预签名访问 URL（含权限校验）。"""
        self._ensure_kb_access(db, user_id, kb_id)
        object_name = f"kb_{kb_id}/images/{image_name}"
        return minio_repo.get_presigned_url(object_name)

    def preview_chunks(
        self, db: Session, request: ChunkPreviewRequest, user_id: int
    ) -> list:
        """预览文件在指定切分参数下的分段结果。"""
        from services.rag_service import rag_service

        file_repo = FileRepo(db)
        kb_repo = KBRepo(db)
        file_entity = file_repo.get_file_by_id(request.file_id)
        if not file_entity:
            raise ResourceNotFoundError(f"文件 ID={request.file_id} 不存在")
        self._ensure_kb_access(db, user_id, file_entity.kb_id)

        kb_entity = kb_repo.get_kb_by_id(file_entity.kb_id)
        if not kb_entity:
            raise ResourceNotFoundError(f"知识库 ID={file_entity.kb_id} 不存在")

        full_text = rag_service._extract_text(file_entity, kb_entity)
        if not full_text or not full_text.strip():
            return []

        separators = request.separators or None
        return rag_service._split_text(
            full_text,
            request.chunk_size,
            request.chunk_overlap,
            file_entity,
            separators,
        )

    def delete_file(self, db: Session, file_id: int, user_id: int) -> None:
        """
        完整删除单个文件：
        1. 删除 Milvus 中该文件所有向量
        2. 删除 MinIO 中该文件对象
        3. 硬删除 MySQL 中 KnowledgeFile / DocumentChunk 记录
        """
        file_repo = FileRepo(db)
        file_entity = file_repo.get_file_by_id(file_id)
        if not file_entity:
            raise ResourceNotFoundError(f"文件 ID={file_id} 不存在或已被删除")
        # 通过角色权限校验访问权限
        self._ensure_kb_access(db, user_id, file_entity.kb_id)

        milvus_repo.delete_chunks_by_file_id(file_entity.kb_id, file_id)
        minio_repo.delete_file(file_entity.minio_object_name)

        file_repo.delete_file(file_id)
        logger.info(f"文件删除完成: file_id={file_id}, name={file_entity.file_name}")

    def delete_chunk(self, db: Session, file_id: int, chunk_id: int, user_id: int) -> None:
        """删除单个文档切片（DB + Milvus）。"""
        file_repo = FileRepo(db)
        file_entity = file_repo.get_file_by_id(file_id)
        if not file_entity:
            raise ResourceNotFoundError(f"文件 ID={file_id} 不存在")
        self._ensure_kb_access(db, user_id, file_entity.kb_id)
        found = file_repo.delete_chunk_by_id(chunk_id, file_id)
        if not found:
            raise ResourceNotFoundError(f"切片 ID={chunk_id} 不存在或不属于文件 ID={file_id}")
        milvus_repo.delete_chunk_by_chunk_id(file_entity.kb_id, chunk_id)
        logger.info(f"切片删除完成: chunk_id={chunk_id}, file_id={file_id}")


# 实例化单例
file_service = FileService()