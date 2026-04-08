from math import ceil

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import get_current_user
from core.config import settings
from core.database import get_db
from core.exceptions import BusinessError, ResourceNotFoundError
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.file_schema import (
    ChunkPageResponse,
    ChunkResponse,
    FilePageResponse,
    FileResponse,
    FileStrategyUpdate,
)
from repositories.file_repo import FileRepo
from repositories.minio_repo import minio_repo
from services.file_service import file_service

router = APIRouter(prefix='/file', tags=['Knowledge File'])


def _validate_upload_files(files: list[UploadFile]) -> None:
    """Validate file sizes and types before processing."""
    allowed = set(settings.ALLOWED_FILE_TYPES)
    max_size = settings.MAX_UPLOAD_FILE_SIZE_BYTES
    for f in files:
        ext = (f.filename or "").rsplit(".", 1)[-1].lower() if f.filename else ""
        if ext not in allowed:
            raise BusinessError(
                f"不支持的文件类型: {ext}，支持的类型: {', '.join(sorted(allowed))}"
            )
        if f.size is not None and f.size > max_size:
            raise BusinessError(
                f"文件 {f.filename} 超出大小限制 ({settings.MAX_UPLOAD_FILE_SIZE_MB}MB)"
            )


@router.post('/upload', response_model=UnifiedResponse[list[dict]], summary='批量上传文件')
async def upload_files(
    kb_id: int = Form(..., description='关联的知识库 ID'),
    files: list[UploadFile] = File(..., description='要上传的文件列表'),
    custom_chunk_size: int | None = Form(None, description='统一指定的自定义切片大小'),
    custom_chunk_overlap: int | None = Form(None, description='统一指定的自定义切片重叠度'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not files:
        raise BusinessError('请至少选择一个文件')

    _validate_upload_files(files)

    if custom_chunk_size is not None and custom_chunk_overlap is not None:  # noqa: SIM102
        if custom_chunk_overlap >= custom_chunk_size:
            raise BusinessError('切片重叠度必须小于切片大小')

    results = await file_service.batch_upload(
        db=db,
        kb_id=kb_id,
        files=files,
        user_id=current_user.id,
        custom_chunk_size=custom_chunk_size,
        custom_chunk_overlap=custom_chunk_overlap,
    )
    return success(data=results, message='批量上传请求已处理')


@router.get('/kb/{kb_id}', response_model=UnifiedResponse[FilePageResponse], summary='获取知识库文件列表')
async def get_kb_files(
    kb_id: int = Path(..., description='知识库 ID'),
    page: int = Query(1, ge=1, description='页码'),
    page_size: int = Query(10, ge=1, le=100, description='每页条数'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = FileRepo(db)
    items, total = repo.get_files_by_kb_paginated(kb_id, page, page_size)
    total_pages = ceil(total / page_size) if total else 0

    return success(
        data=FilePageResponse(
            items=[FileResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
        message='获取知识库文件列表成功',
    )


@router.delete('/{file_id}', response_model=UnifiedResponse[None], summary='删除文件')
async def delete_file(
    file_id: int = Path(..., description='文件 ID'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_service.delete_file(db, file_id, current_user.id)
    return success(data=None, message='文件删除成功')


@router.get('/{file_id}/chunks', response_model=UnifiedResponse[ChunkPageResponse], summary='预览文件分段内容')
async def get_file_chunks(
    file_id: int = Path(..., description='文件 ID'),
    page: int = Query(1, ge=1, description='页码'),
    page_size: int = Query(20, ge=1, le=100, description='每页分段数'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = FileRepo(db)
    file_entity = repo.get_file_by_id(file_id)
    if not file_entity:
        raise ResourceNotFoundError('文件不存在或已被删除')

    chunks, total = repo.get_chunks_by_file_id_paginated(file_id, page, page_size)
    total_pages = ceil(total / page_size) if total else 0

    return success(
        data=ChunkPageResponse(
            items=[ChunkResponse.model_validate(chunk) for chunk in chunks],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
        message='获取文件分段成功',
    )


@router.put('/{file_id}/strategy', response_model=UnifiedResponse[FileResponse], summary='修改单独文件的切分策略')
async def update_file_strategy(
    strategy_in: FileStrategyUpdate,
    file_id: int = Path(..., description='文件 ID'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = FileRepo(db)
    file_entity = repo.get_file_by_id(file_id)

    if not file_entity:
        raise ResourceNotFoundError('文件不存在或已被删除')

    file_entity.custom_chunk_size = strategy_in.custom_chunk_size
    file_entity.custom_chunk_overlap = strategy_in.custom_chunk_overlap
    file_entity.status = 0
    file_entity.error_msg = None

    # Bug 修复：先 commit 再触发 Celery 任务，避免 Celery 读取到未提交的状态
    db.commit()
    db.refresh(file_entity)

    from tasks.document_tasks import reprocess_document_task
    reprocess_document_task.delay(file_id)

    return success(data=file_entity, message='文件切分策略已更新，正在后台重新解析')


@router.get('/image/{kb_id}/{image_name}', summary='获取知识库图片（临时签名重定向）')
async def get_image(
    kb_id: int = Path(..., description='知识库 ID'),
    image_name: str = Path(..., description='图片文件名'),
    current_user: User = Depends(get_current_user),
):
    """Generate a short-lived presigned URL for an image stored in MinIO and redirect."""
    object_name = f"kb_{kb_id}/images/{image_name}"
    url = minio_repo.get_presigned_url(object_name, expires_hours=2)
    return RedirectResponse(url=url)
