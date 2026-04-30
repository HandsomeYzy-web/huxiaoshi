from typing import Optional

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from core.database import get_db
from core.exceptions import AuthenticationError, PermissionDeniedError
from core.security import decode_access_token
from models.entities.user import User
from repositories.user_repo import UserRepo

# TODO:如果用户量很大怎么办，引入redis
def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("未提供认证令牌")
    token = authorization.removeprefix("Bearer ")
    user_id = decode_access_token(token)
    if user_id is None:
        raise AuthenticationError("令牌无效或已过期")
    user = UserRepo(db).get_by_id(user_id)
    if not user or not user.is_active:
        raise AuthenticationError("用户不存在或已被禁用")
    return user

# TODO:同上
def require_permission(permission_code: str):
    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        from services.role_service import role_service

        perms = role_service.get_user_permissions(db, current_user.id)
        if permission_code not in perms:
            raise PermissionDeniedError(f"您没有权限执行此操作（需要: {permission_code}）")
        return current_user

    return checker
