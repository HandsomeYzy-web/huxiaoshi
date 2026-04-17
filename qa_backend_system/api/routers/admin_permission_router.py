from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.dependencies import get_current_user, require_permission
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.admin_schema import PermissionCreate, PermissionResponse, PermissionTreeNode, PermissionUpdate
from services.permission_service import permission_service
from services.role_service import role_service

router = APIRouter(prefix="/permissions", tags=["Admin"])


@router.get("", response_model=UnifiedResponse[List[PermissionResponse]])
async def list_permissions(
    module: str | None = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("permission.view")),
):
    return success(data=permission_service.list_permissions(db, module), message="Fetched permissions")


@router.post("", response_model=UnifiedResponse[PermissionResponse])
async def create_permission(
    req: PermissionCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("permission.create")),
):
    return success(data=permission_service.create_permission(db, req), message="Permission created")


@router.get("/{code}", response_model=UnifiedResponse[PermissionResponse])
async def get_permission(
    code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("permission.view")),
):
    return success(data=permission_service.get_permission(db, code), message="Fetched permission")


@router.put("/{code}", response_model=UnifiedResponse[PermissionResponse])
async def update_permission(
    code: str,
    req: PermissionUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("permission.update")),
):
    return success(data=permission_service.update_permission(db, code, req), message="Permission updated")


@router.delete("/{code}", response_model=UnifiedResponse[None])
async def delete_permission(
    code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("permission.delete")),
):
    permission_service.delete_permission(db, code)
    return success(data=None, message="Permission deleted")


@router.get("/tree/full", response_model=UnifiedResponse[List[PermissionTreeNode]])
async def get_full_permission_tree(
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("permission.view")),
):
    return success(data=permission_service.build_full_tree(db), message="Fetched permission tree")


@router.get("/tree/user", response_model=UnifiedResponse[List[PermissionTreeNode]])
async def get_user_permission_tree(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_perms = role_service.get_user_permissions(db, current_user.id)
    return success(data=permission_service.build_permission_tree(db, user_perms), message="Fetched user permission tree")
