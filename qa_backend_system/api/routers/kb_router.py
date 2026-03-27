from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from models.schemas.kb_schema import KBCreate, KBResponse
from services.kb_service import kb_service
from core.response import UnifiedResponse, success

from typing import List
from repositories.meta_repo import MetaRepo

router = APIRouter(prefix="/kb", tags=["Knowledge Base"])

@router.post("", response_model=UnifiedResponse[KBResponse], summary="创建新的知识库")
async def create_knowledge_base(
    kb_in: KBCreate,
    db: Session = Depends(get_db)
):
    """
    创建一个新的知识库，可以指定该知识库下文件的默认切分策略。
    - **name**: 知识库名称 (必填，且必须唯一)
    - **description**: 描述 (选填)
    - **default_chunk_size**: 默认切片大小 (默认 1000)
    - **default_chunk_overlap**: 默认切片重叠度 (默认 200)
    """
    # 直接调用 Service 层处理业务逻辑
    created_kb = kb_service.create_kb(db, kb_in)
    return success(data=created_kb, message="知识库创建成功")

@router.get("", response_model=UnifiedResponse[List[KBResponse]], summary="获取所有知识库列表")
async def get_all_knowledge_bases(db: Session = Depends(get_db)):
    """
    获取系统中所有未被删除的知识库，按创建时间倒序排列。
    """
    repo = MetaRepo(db)
    kbs = repo.get_all_kbs()
    return success(data=kbs, message="获取知识库列表成功")