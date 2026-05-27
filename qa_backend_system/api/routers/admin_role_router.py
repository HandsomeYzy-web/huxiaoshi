from typing import List

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from api.dependencies import invalidate_all_kb_access_cache, invalidate_kb_access_cache, invalidate_user_perms_cache, require_permission
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.admin_schema import RoleCreate, RolePermissionSet, RoleResponse, RoleUpdate
from repositories.role_repo import RoleRepo
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
    result = role_service.update_role(db, role_id, req)
    # 角色状态或信息变更可能影响用户权限与 KB 访问，使受影响用户缓存失效
    user_ids = RoleRepo(db).get_user_ids_by_role(role_id)
    for uid in user_ids:
        invalidate_user_perms_cache(uid)
        invalidate_kb_access_cache(uid)
    return success(data=result, message="Role updated")


@router.delete("/{role_id}", response_model=UnifiedResponse[None])
async def delete_role(
    role_id: int = Path(...),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("role.delete")),
):
    # 删除角色前先取出受影响用户列表，删除后缓存失效
    user_ids = RoleRepo(db).get_user_ids_by_role(role_id)
    role_service.delete_role(db, role_id)
    for uid in user_ids:
        invalidate_user_perms_cache(uid)
        invalidate_kb_access_cache(uid)
    # KB 访问授权也可能关联了此角色，全量失效一次
    invalidate_all_kb_access_cache()
    return success(data=None, message="Role deleted")


@router.put("/{role_id}/permissions", response_model=UnifiedResponse[None])
async def set_role_permissions(
    req: RolePermissionSet,
    role_id: int = Path(...),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("role.assign")),
):
    role_service.set_role_permissions(db, role_id, req.permission_codes)
    # 角色权限变更后，使该角色下所有用户的权限缓存失效
    user_ids = RoleRepo(db).get_user_ids_by_role(role_id)
    for uid in user_ids:
        invalidate_user_perms_cache(uid)
    return success(data=None, message="Role permissions updated")
