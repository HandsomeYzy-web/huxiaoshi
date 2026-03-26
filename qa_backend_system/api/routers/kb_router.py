from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from models.schemas.kb_schema import KBCreate, KBResponse
from services.kb_service import kb_service

router = APIRouter(prefix="/kb", tags=["Knowledge Base"])

@router.post("", response_model=KBResponse, summary="创建新的知识库")
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
    return kb_service.create_kb(db, kb_in)