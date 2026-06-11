from typing import List

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_id
from core.database import get_db
from core.response import UnifiedResponse, success
from models.schemas.kb_schema import KBCreate, KBResponse, KBUpdate
from services.kb_service import kb_service

router = APIRouter(prefix="/kb", tags=["Knowledge Base"])


@router.post("", response_model=UnifiedResponse[KBResponse])
async def create_knowledge_base(
    kb_in: KBCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return success(data=kb_service.create_kb(db, kb_in, user_id), message="Knowledge base created")


@router.get("", response_model=UnifiedResponse[List[KBResponse]])
async def get_all_knowledge_bases(db: Session = Depends(get_db)):
    return success(data=kb_service.list_kbs(db), message="Fetched knowledge bases")


@router.delete("/{kb_id}", response_model=UnifiedResponse[None])
async def delete_knowledge_base(
    kb_id: int = Path(..., description="Knowledge base ID"),
    db: Session = Depends(get_db),
):
    kb_service.delete_kb(db, kb_id)
    return success(data=None, message="Knowledge base deleted")


@router.patch("/{kb_id}", response_model=UnifiedResponse[KBResponse])
async def update_knowledge_base(
    kb_update: KBUpdate,
    kb_id: int = Path(..., description="Knowledge base ID"),
    db: Session = Depends(get_db),
):
    return success(data=kb_service.update_kb(db, kb_id, kb_update), message="Knowledge base updated")
