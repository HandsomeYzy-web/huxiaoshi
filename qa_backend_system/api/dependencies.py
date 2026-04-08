
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from core.database import get_db
from core.exceptions import AuthenticationError, PermissionDeniedError
from core.security import decode_access_token
from models.entities.user import User
from repositories.user_repo import UserRepo


def get_current_user(
    authorization: str | None = Header(None),
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


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """仅允许管理员访问"""
    if not current_user.is_admin:
        raise PermissionDeniedError("该操作需要管理员权限")
    return current_user


def require_permission(permission_code: str):
    """工厂函数：返回检查特定权限的依赖项"""
    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if current_user.is_admin:
            return current_user
        from services.role_service import role_service
        perms = role_service.get_user_permissions(db, current_user.id)
        if permission_code not in perms:
            raise PermissionDeniedError(f"您没有权限执行此操作（需要: {permission_code}）")
        return current_user
    return checker

