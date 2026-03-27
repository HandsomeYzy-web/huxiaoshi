from typing import List, Optional, Any
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, Path
from sqlalchemy.orm import Session

from core.database import get_db
from core.response import UnifiedResponse, success  # 👈 引入统一响应模型与快捷函数
from models.schemas.file_schema import FileResponse, FileStrategyUpdate
from services.file_service import file_service
from repositories.meta_repo import MetaRepo

router = APIRouter(prefix="/file", tags=["Knowledge File"])

@router.post("/upload", response_model=UnifiedResponse[List[dict]], summary="批量上传文件")
async def upload_files(
        kb_id: int = Form(..., description="关联的知识库 ID"),
        files: List[UploadFile] = File(..., description="要上传的文件列表"),
        custom_chunk_size: Optional[int] = Form(None, description="统一指定的自定义切片大小"),
        custom_chunk_overlap: Optional[int] = Form(None, description="统一指定的自定义切片重叠度"),
        db: Session = Depends(get_db)
):
    """
    支持批量上传文件到指定知识库。
    如果在上传时指定了切分策略，这批文件将统一使用该策略；如果不指定，则使用知识库的默认策略。
    内置了基于 MD5 的防重复上传校验。
    """
    if not files:
        raise HTTPException(status_code=400, detail="请至少选择一个文件")

    results = await file_service.batch_upload(
        db=db,
        kb_id=kb_id,
        files=files,
        custom_chunk_size=custom_chunk_size,
        custom_chunk_overlap=custom_chunk_overlap
    )

    # 重点：使用 success 包裹返回数据
    return success(data=results, message="批量上传请求已处理")

@router.get("/kb/{kb_id}", response_model=UnifiedResponse[List[FileResponse]], summary="获取知识库文件列表")
async def get_kb_files(
        kb_id: int = Path(..., description="知识库 ID"),
        db: Session = Depends(get_db)
):
    """
    获取指定知识库下的所有文件及其当前处理状态。
    状态码：0-待处理, 1-解析中, 2-已完成, 3-解析失败。
    前端可以通过轮询此接口来更新文件的解析进度条。
    """
    repo = MetaRepo(db)
    files = repo.get_files_by_kb(kb_id)

    return success(data=files, message="获取知识库文件列表成功")


@router.put("/{file_id}/strategy", response_model=UnifiedResponse[FileResponse], summary="修改单独文件的切分策略")
async def update_file_strategy(
        strategy_in: FileStrategyUpdate,
        file_id: int = Path(..., description="文件 ID"),
        db: Session = Depends(get_db)
):
    """
    当用户发现某个文件的切分效果不理想时，可以单独修改该文件的切分策略。
    调用此接口后，后端会：
    1. 在 Milvus 中删除该文件旧的向量数据。
    2. 更新 MySQL 中的策略配置。
    3. 将文件状态重置为“待处理(0)”，并重新放入后台异步队列重新解析。
    """
    repo = MetaRepo(db)
    file_entity = repo.get_file_by_id(file_id)

    if not file_entity:
        raise HTTPException(status_code=404, detail="文件不存在或已被删除")

    file_entity.custom_chunk_size = strategy_in.custom_chunk_size
    file_entity.custom_chunk_overlap = strategy_in.custom_chunk_overlap

    file_entity.status = 0
    file_entity.error_msg = None

    # ----------------------------------------------------
    # 触发 Celery 异步任务：清理 Milvus 旧数据并重新解析
    from tasks.document_tasks import reprocess_document_task
    reprocess_document_task.delay(file_id)
    # ----------------------------------------------------

    db.commit()
    db.refresh(file_entity)

    return success(data=file_entity, message="文件切分策略已更新，正在后台重新解析")