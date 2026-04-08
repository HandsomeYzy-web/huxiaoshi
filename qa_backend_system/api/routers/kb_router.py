
from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from api.dependencies import get_current_user
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.kb_schema import KBCreate, KBResponse, KBUpdate
from services.kb_service import kb_service

router = APIRouter(prefix="/kb", tags=["Knowledge Base"])


@router.post("", response_model=UnifiedResponse[KBResponse], summary="创建新的知识库")
async def create_knowledge_base(
    kb_in: KBCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    created_kb = kb_service.create_kb(db, kb_in, current_user.id)
    return success(data=created_kb, message="知识库创建成功")


@router.get("", response_model=UnifiedResponse[list[KBResponse]], summary="获取所有知识库列表")
async def get_all_knowledge_bases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kbs = kb_service.list_kbs(db, current_user.id)
    return success(data=kbs, message="获取知识库列表成功")


@router.delete("/{kb_id}", response_model=UnifiedResponse[None], summary="删除知识库")
async def delete_knowledge_base(
    kb_id: int = Path(..., description="知识库 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb_service.delete_kb(db, kb_id, current_user.id)
    return success(data=None, message="知识库删除成功")


@router.patch("/{kb_id}", response_model=UnifiedResponse[KBResponse], summary="更新知识库配置")
async def update_knowledge_base(
    kb_update: KBUpdate,
    kb_id: int = Path(..., description="知识库 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = kb_service.update_kb(db, kb_id, kb_update, current_user.id)
    return success(data=updated, message="知识库更新成功")
