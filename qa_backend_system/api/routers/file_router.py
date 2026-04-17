from math import ceil
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.dependencies import get_current_user, require_permission
from core.config import settings
from core.database import get_db
from core.exceptions import BusinessError, ResourceNotFoundError
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.file_schema import (
    ChunkPageResponse,
    ChunkPreviewRequest,
    ChunkPreviewResponse,
    ChunkResponse,
    FilePageResponse,
    FileResponse,
    FileStrategyUpdate,
)
from repositories.file_repo import FileRepo
from repositories.kb_repo import KBRepo
from repositories.minio_repo import minio_repo
from services.file_service import file_service
from services.kb_access_service import kb_access_service

router = APIRouter(
    prefix="/file",
    tags=["Knowledge File"],
    dependencies=[Depends(require_permission("workspace.file"))],
)


def _validate_upload_files(files: List[UploadFile]) -> None:
    allowed = set(settings.ALLOWED_FILE_TYPES)
    max_size = settings.MAX_UPLOAD_FILE_SIZE_BYTES
    for file in files:
        ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
        if ext not in allowed:
            raise BusinessError(f"Unsupported file type: {ext}")
        if file.size is not None and file.size > max_size:
            raise BusinessError(f"File {file.filename} exceeds max size")


def _ensure_user_can_access_kb(db: Session, user_id: int, kb_id: int) -> None:
    accessible_kb_ids = kb_access_service.get_accessible_kb_ids(db, user_id)
    if accessible_kb_ids is not None and kb_id not in accessible_kb_ids:
        raise ResourceNotFoundError(f"Knowledge base {kb_id} not found or not accessible")


@router.post("/upload", response_model=UnifiedResponse[List[dict]])
async def upload_files(
    kb_id: int = Form(...),
    files: List[UploadFile] = File(...),
    custom_chunk_size: Optional[int] = Form(None),
    custom_chunk_overlap: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not files:
        raise BusinessError("At least one file is required")
    _validate_upload_files(files)
    if custom_chunk_size is not None and custom_chunk_overlap is not None and custom_chunk_overlap >= custom_chunk_size:
        raise BusinessError("Chunk overlap must be smaller than chunk size")
    return success(
        data=await file_service.batch_upload(
            db=db,
            kb_id=kb_id,
            files=files,
            user_id=current_user.id,
            custom_chunk_size=custom_chunk_size,
            custom_chunk_overlap=custom_chunk_overlap,
        ),
        message="Upload processed",
    )


@router.get("/kb/{kb_id}", response_model=UnifiedResponse[FilePageResponse])
async def get_kb_files(
    kb_id: int = Path(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_user_can_access_kb(db, current_user.id, kb_id)
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
        message="Fetched files",
    )


@router.delete("/{file_id}", response_model=UnifiedResponse[None])
async def delete_file(
    file_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_service.delete_file(db, file_id, current_user.id)
    return success(data=None, message="File deleted")


@router.get("/{file_id}/chunks", response_model=UnifiedResponse[ChunkPageResponse])
async def get_file_chunks(
    file_id: int = Path(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = FileRepo(db)
    file_entity = repo.get_file_by_id(file_id)
    if not file_entity:
        raise ResourceNotFoundError("File not found")
    _ensure_user_can_access_kb(db, current_user.id, file_entity.kb_id)
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
        message="Fetched file chunks",
    )


@router.put("/{file_id}/strategy", response_model=UnifiedResponse[FileResponse])
async def update_file_strategy(
    strategy_in: FileStrategyUpdate,
    file_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = FileRepo(db)
    file_entity = repo.get_file_by_id(file_id)
    if not file_entity:
        raise ResourceNotFoundError("File not found")
    _ensure_user_can_access_kb(db, current_user.id, file_entity.kb_id)

    file_entity.custom_chunk_size = strategy_in.custom_chunk_size
    file_entity.custom_chunk_overlap = strategy_in.custom_chunk_overlap
    if strategy_in.custom_separators is not None:
        import json

        file_entity.custom_separators = json.dumps(strategy_in.custom_separators, ensure_ascii=False)
    file_entity.status = 0
    file_entity.error_msg = None
    db.commit()
    db.refresh(file_entity)

    from tasks.document_tasks import reprocess_document_task

    reprocess_document_task.delay(file_id)
    return success(data=file_entity, message="File strategy updated")


@router.get("/image/{kb_id}/{image_name}")
async def get_image(
    kb_id: int = Path(...),
    image_name: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_user_can_access_kb(db, current_user.id, kb_id)
    object_name = f"kb_{kb_id}/images/{image_name}"
    return RedirectResponse(url=minio_repo.get_presigned_url(object_name, expires_hours=2))


@router.post("/preview-chunks", response_model=UnifiedResponse[ChunkPreviewResponse])
async def preview_file_chunks(
    request: ChunkPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from models.schemas.file_schema import ChunkPreviewItem
    from services.rag_service import rag_service

    repo = FileRepo(db)
    file_entity = repo.get_file_by_id(request.file_id)
    if not file_entity:
        raise ResourceNotFoundError("File not found")
    _ensure_user_can_access_kb(db, current_user.id, file_entity.kb_id)

    kb_entity = KBRepo(db).get_kb_by_id(file_entity.kb_id)
    if not kb_entity:
        raise ResourceNotFoundError("Knowledge base not found")

    full_text = rag_service._extract_text(file_entity, kb_entity)
    if not full_text or not full_text.strip():
        raise BusinessError("No text extracted from file")

    separators = request.separators or ["\n\n", "\n", "。", "，", " ", ""]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        separators=separators,
    )
    chunks = splitter.split_documents([Document(page_content=full_text)])
    preview_items = [
        ChunkPreviewItem(index=index, content=chunk.page_content, char_count=len(chunk.page_content))
        for index, chunk in enumerate(chunks)
    ]
    return success(
        data=ChunkPreviewResponse(
            total_chunks=len(preview_items),
            chunks=preview_items,
            total_chars=sum(item.char_count for item in preview_items),
        ),
        message="Preview generated",
    )
