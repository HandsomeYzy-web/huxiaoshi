from typing import List

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from api.dependencies import require_permission
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.admin_schema import RoleCreate, RolePermissionSet, RoleResponse, RoleUpdate
from services.role_service import role_service

router = APIRouter(prefix="/roles", tags=["Admin"])


@router.get("", response_model=UnifiedResponse[List[RoleResponse]])
async def list_roles(db: Session = Depends(get_db), _user: User = Depends(require_permission("role.view"))):
    return success(data=role_service.list_roles(db), message="Fetched roles")


@router.post("", response_model=UnifiedResponse[RoleResponse])
async def create_role(req: RoleCreate, db: Session = Depends(get_db), _user: User = Depends(require_permission("role.create"))):
    return success(data=role_service.create_role(db, req), message="Role created")


@router.put("/{role_id}", response_model=UnifiedResponse[RoleResponse])
async def update_role(
    req: RoleUpdate,
    role_id: int = Path(...),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("role.update")),
):
    return success(data=role_service.update_role(db, role_id, req), message="Role updated")


@router.delete("/{role_id}", response_model=UnifiedResponse[None])
async def delete_role(
    role_id: int = Path(...),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("role.delete")),
):
    role_service.delete_role(db, role_id)
    return success(data=None, message="Role deleted")


@router.put("/{role_id}/permissions", response_model=UnifiedResponse[None])
async def set_role_permissions(
    req: RolePermissionSet,
    role_id: int = Path(...),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("role.assign")),
):
    role_service.set_role_permissions(db, role_id, req.permission_codes)
    return success(data=None, message="Role permissions updated")
