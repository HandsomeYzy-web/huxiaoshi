from typing import List

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from api.dependencies import invalidate_all_kb_access_cache, require_permission
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.admin_schema import KBAccessResponse, KBAccessSet
from services.kb_access_service import kb_access_service

router = APIRouter(prefix="/kb", tags=["Admin"])


@router.put("/{kb_id}/access", response_model=UnifiedResponse[None])
async def set_kb_access(
    req: KBAccessSet,
    kb_id: int = Path(...),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("kb_access.assign")),
):
    kb_access_service.set_kb_access(db, kb_id, req.role_ids)
    invalidate_all_kb_access_cache()
    return success(data=None, message="KB access updated")


@router.get("/{kb_id}/access", response_model=UnifiedResponse[KBAccessResponse])
async def get_kb_access(
    kb_id: int = Path(...),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("kb_access.view")),
):
    role_ids = kb_access_service.get_kb_access(db, kb_id)
    return success(data={"kb_id": kb_id, "accessible_role_ids": role_ids}, message="Fetched KB access")


@router.get("/access/all", response_model=UnifiedResponse[List[KBAccessResponse]])
async def get_all_kb_access(db: Session = Depends(get_db), _user: User = Depends(require_permission("kb_access.view"))):
    return success(data=kb_access_service.get_all_kb_access(db), message="Fetched KB access map")
