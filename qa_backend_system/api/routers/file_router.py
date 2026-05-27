from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import get_current_user, require_kb_access, require_permission
from core.config import settings
from core.database import get_db
from core.exceptions import BusinessError
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.file_schema import (
    ChunkPageResponse,
    ChunkPreviewRequest,
    ChunkPreviewResponse,
    ChunkResponse,
    FilePageResponse,
    FileRenameRequest,
    FileResponse,
    FileStrategyUpdate,
)
from models.schemas.file_schema import ChunkPreviewItem
from services.file_service import file_service

router = APIRouter(
    prefix="/file",
    tags=["Knowledge File"],
    dependencies=[Depends(require_permission("workspace.file"))],
)

LEGACY_OFFICE_TYPES = {"doc", "xls", "ppt"}


def _validate_upload_files(files: List[UploadFile]) -> None:
    allowed = set(settings.ALLOWED_FILE_TYPES)
    max_size = settings.MAX_UPLOAD_FILE_SIZE_BYTES
    for f in files:
        ext = (f.filename or "").rsplit(".", 1)[-1].lower() if f.filename else ""
        if ext in LEGACY_OFFICE_TYPES:
            target_ext = "docx" if ext == "doc" else "xlsx" if ext == "xls" else "pptx"
            raise BusinessError(f"暂不支持旧版 Office 文件 {f.filename}，请先转换为 .{target_ext} 后再上传")
        if ext not in allowed:
            raise BusinessError(f"不支持的文件类型: {ext}")
        if f.size is not None and f.size > max_size:
            raise BusinessError(f"文件 {f.filename} 超过大小限制")


@router.post("/upload", response_model=UnifiedResponse[List[dict]], dependencies=[Depends(require_permission("file.upload"))])
async def upload_files(
    kb_id: int = Form(...),
    files: List[UploadFile] = File(...),
    custom_chunk_size: Optional[int] = Form(None),
    custom_chunk_overlap: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not files:
        raise BusinessError("至少上传一个文件")
    _validate_upload_files(files)
    if custom_chunk_size is not None and custom_chunk_overlap is not None and custom_chunk_overlap >= custom_chunk_size:
        raise BusinessError("切片重叠度必须小于切片大小")
    return success(
        data=await file_service.batch_upload(
            db=db,
            kb_id=kb_id,
            files=files,
            user_id=current_user.id,
            custom_chunk_size=custom_chunk_size,
            custom_chunk_overlap=custom_chunk_overlap,
        ),
        message="上传处理完成",
    )


@router.get("/kb/{kb_id}", response_model=UnifiedResponse[FilePageResponse], dependencies=[Depends(require_kb_access)])
async def get_kb_files(
    kb_id: int = Path(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total, total_pages = file_service.list_kb_files(db, kb_id, current_user.id, page, page_size)
    return success(
        data=FilePageResponse(
            items=[FileResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
        message="获取文件列表成功",
    )


@router.delete("/{file_id}", response_model=UnifiedResponse[None], dependencies=[Depends(require_permission("file.delete"))])
async def delete_file(
    file_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_service.delete_file(db, file_id, current_user.id)
    return success(data=None, message="File deleted")


@router.delete("/{file_id}/chunks/{chunk_id}", response_model=UnifiedResponse[None], dependencies=[Depends(require_permission("file.delete"))])
async def delete_chunk(
    file_id: int = Path(...),
    chunk_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_service.delete_chunk(db, file_id, chunk_id, current_user.id)
    return success(data=None, message="切片已删除")


@router.get("/{file_id}/chunks", response_model=UnifiedResponse[ChunkPageResponse])
async def get_file_chunks(
    file_id: int = Path(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chunks, total, total_pages = file_service.get_file_chunks(db, file_id, current_user.id, page, page_size)
    return success(
        data=ChunkPageResponse(
            items=[ChunkResponse.model_validate(chunk) for chunk in chunks],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
        message="获取分段列表成功",
    )


@router.put("/{file_id}/strategy", response_model=UnifiedResponse[FileResponse], dependencies=[Depends(require_permission("file.reprocess"))])
async def update_file_strategy(
    strategy_in: FileStrategyUpdate,
    file_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_entity = file_service.update_file_strategy(db, file_id, strategy_in, current_user.id)
    return success(data=FileResponse.model_validate(file_entity), message="切分策略已更新，重新解析任务已触发")


@router.get("/image/{kb_id}/{image_name}")
async def get_image(
    kb_id: int = Path(...),
    image_name: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    url = file_service.get_image_url(db, kb_id, image_name, current_user.id)
    return RedirectResponse(url=url)


@router.post("/preview-chunks", response_model=UnifiedResponse[ChunkPreviewResponse])
async def preview_file_chunks(
    request: ChunkPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """预览文件切分结果（供调试使用）。"""
    chunks = file_service.preview_chunks(db, request, current_user.id)
    preview_items = [
        ChunkPreviewItem(index=i, content=c.page_content, char_count=len(c.page_content))
        for i, c in enumerate(chunks)
    ]
    return success(
        data=ChunkPreviewResponse(
            total_chunks=len(preview_items),
            chunks=preview_items,
            total_chars=sum(item.char_count for item in preview_items),
        ),
        message="预览生成成功",
    )
