from typing import List, Optional
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, Path
from sqlalchemy.orm import Session

from core.database import get_db
from models.schemas.file_schema import FileResponse, FileStrategyUpdate
from services.file_service import file_service
from repositories.meta_repo import MetaRepo
from tasks.document_tasks import reprocess_document_task

router = APIRouter(prefix="/file", tags=["Knowledge File"])


# ==========================================
# 1. 批量上传文件到知识库
# ==========================================
@router.post("/upload", summary="批量上传文件")
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

    # 调用 Service 层执行防重校验、上传 MinIO 和写入 MySQL
    results = await file_service.batch_upload(
        db=db,
        kb_id=kb_id,
        files=files,
        custom_chunk_size=custom_chunk_size,
        custom_chunk_overlap=custom_chunk_overlap
    )
    return {"message": "批量上传请求已处理", "data": results}


# ==========================================
# 2. 查询某知识库下的所有文件列表
# ==========================================
@router.get("/kb/{kb_id}", response_model=List[FileResponse], summary="获取知识库文件列表")
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
    return files


# ==========================================
# 3. 单独修改某一个文件的切分策略 (并触发重算)
# ==========================================
@router.put("/{file_id}/strategy", response_model=FileResponse, summary="修改单独文件的切分策略")
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

    # 更新策略
    file_entity.custom_chunk_size = strategy_in.custom_chunk_size
    file_entity.custom_chunk_overlap = strategy_in.custom_chunk_overlap

    # 状态回退为 0 (待处理)，准备重新触发解析
    file_entity.status = 0
    file_entity.error_msg = None

    reprocess_document_task.delay(file_id)

    db.commit()
    db.refresh(file_entity)
    return file_entity