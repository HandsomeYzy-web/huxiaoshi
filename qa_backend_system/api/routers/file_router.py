from math import ceil
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile
from sqlalchemy.orm import Session

from core.database import get_db
from core.response import UnifiedResponse, success
from models.schemas.file_schema import FilePageResponse, FileResponse, FileStrategyUpdate
from repositories.meta_repo import MetaRepo
from services.file_service import file_service

router = APIRouter(prefix='/file', tags=['Knowledge File'])


@router.post('/upload', response_model=UnifiedResponse[List[dict]], summary='批量上传文件')
async def upload_files(
    kb_id: int = Form(..., description='关联的知识库 ID'),
    files: List[UploadFile] = File(..., description='要上传的文件列表'),
    custom_chunk_size: Optional[int] = Form(None, description='统一指定的自定义切片大小'),
    custom_chunk_overlap: Optional[int] = Form(None, description='统一指定的自定义切片重叠度'),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail='请至少选择一个文件')

    results = await file_service.batch_upload(
        db=db,
        kb_id=kb_id,
        files=files,
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
):
    repo = MetaRepo(db)
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


@router.put('/{file_id}/strategy', response_model=UnifiedResponse[FileResponse], summary='修改单独文件的切分策略')
async def update_file_strategy(
    strategy_in: FileStrategyUpdate,
    file_id: int = Path(..., description='文件 ID'),
    db: Session = Depends(get_db),
):
    repo = MetaRepo(db)
    file_entity = repo.get_file_by_id(file_id)

    if not file_entity:
        raise HTTPException(status_code=404, detail='文件不存在或已被删除')

    file_entity.custom_chunk_size = strategy_in.custom_chunk_size
    file_entity.custom_chunk_overlap = strategy_in.custom_chunk_overlap
    file_entity.status = 0
    file_entity.error_msg = None

    from tasks.document_tasks import reprocess_document_task

    reprocess_document_task.delay(file_id)

    db.commit()
    db.refresh(file_entity)

    return success(data=file_entity, message='文件切分策略已更新，正在后台重新解析')
