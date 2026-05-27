from typing import List

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from api.dependencies import invalidate_kb_access_cache, invalidate_user_perms_cache, require_permission
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.admin_schema import UserAdminResponse, UserRoleAssign
from services.role_service import role_service

router = APIRouter(prefix="/users", tags=["Admin"])


@router.get("", response_model=UnifiedResponse[List[UserAdminResponse]])
async def list_users(db: Session = Depends(get_db), _user: User = Depends(require_permission("user.view"))):
    return success(data=role_service.list_users(db), message="Fetched users")


@router.put("/{user_id}/roles", response_model=UnifiedResponse[None])
async def set_user_roles(
    req: UserRoleAssign,
    user_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("user.assign")),
):
    role_service.set_user_roles(db, user_id, req.role_ids, assigned_by=current_user.id)
    # 角色变更后将权限缓存和 KB 访问权限缓存同时失效
    invalidate_user_perms_cache(user_id)
    invalidate_kb_access_cache(user_id)
    return success(data=None, message="User roles updated")
