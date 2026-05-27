from typing import List, Optional

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from core.database import get_db
from core.exceptions import AuthenticationError, PermissionDeniedError
from core.security import decode_access_token
from models.entities.user import User
from repositories.kb_access_repo import get_accessible_kb_ids as _get_accessible_kb_ids
from repositories.redis_repo import redis_repo
from repositories.user_repo import UserRepo

# 权限缓存 TTL（秒），5分钟内不重复查数据库
_PERMS_CACHE_TTL = 300


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


def require_permission(permission_code: str):
    """检查当前用户是否拥有指定权限码，权限集合优先从 Redis 缓存读取。"""
    def checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        cache_key = f"perms:{current_user.id}"
        cached = redis_repo.get_list(cache_key)
        if cached is not None:
            perms: set[str] = set(cached)
        else:
            from services.role_service import role_service
            perms = role_service.get_user_permissions(db, current_user.id)
            redis_repo.set_list(cache_key, list(perms), expire_seconds=_PERMS_CACHE_TTL)

        if permission_code not in perms:
            raise PermissionDeniedError(f"您没有权限执行此操作（需要: {permission_code}）")
        return current_user

    return checker


def require_kb_access(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> int:
    """验证当前用户是否有权访问指定知识库（自己创建 + 角色授权均可通过）。

    - kb_id 由 FastAPI 从路径参数 {kb_id} 自动绑定。
    - 可访问的 KB ID 集合优先从 Redis 缓存读取（TTL 5 分钟），未命中时查 DB 并回填缓存。
    - 验证通过后返回 kb_id，可直接作为端点参数值使用。
    """
    accessible = _get_accessible_kb_ids(db, current_user.id)
    if kb_id not in accessible:
        raise PermissionDeniedError("您没有权限访问该知识库")
    return kb_id


def get_accessible_kb_ids(db: Session, user_id: int) -> list[int]:
    """获取用户可访问的知识库 ID 列表（含自己创建 + 角色授权），优先从 Redis 缓存读取。"""
    return _get_accessible_kb_ids(db, user_id)


def list_accessible_kb_ids(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[int]:
    """FastAPI 依赖：返回当前用户可访问的知识库 ID 列表（供路由注入使用）。"""
    return _get_accessible_kb_ids(db, current_user.id)


def invalidate_user_perms_cache(user_id: int) -> None:
    """主动使某用户的权限缓存失效（角色变更时调用）。"""
    redis_repo.delete(f"perms:{user_id}")


def invalidate_kb_access_cache(user_id: int) -> None:
    """使某用户的知识库访问权限缓存失效（用户角色变更时调用）。"""
    redis_repo.delete(f"kb_access:{user_id}")


def invalidate_all_kb_access_cache() -> None:
    """使所有用户的知识库访问权限缓存失效（KB 授权配置变更时调用）。"""
    redis_repo.delete_pattern("kb_access:*")
