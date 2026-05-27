from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models.entities.kb_role_access import KBRoleAccess
from models.entities.knowledge_base import KnowledgeBase
from models.entities.role import Role
from models.entities.user_role import UserRole

# 知识库访问权限缓存 TTL（秒），5 分钟
KB_ACCESS_CACHE_TTL = 300


class KBAccessRepo:
    def __init__(self, db: Session):
        self.db = db

    def set_kb_role_access(self, kb_id: int, role_ids: list[int]) -> None:
        self.db.execute(delete(KBRoleAccess).where(KBRoleAccess.kb_id == kb_id))
        for role_id in role_ids:
            self.db.add(KBRoleAccess(kb_id=kb_id, role_id=role_id))
        self.db.commit()

    def get_kb_accessible_role_ids(self, kb_id: int) -> list[int]:
        stmt = select(KBRoleAccess.role_id).where(KBRoleAccess.kb_id == kb_id)
        return list(self.db.scalars(stmt).all())

    def get_accessible_kb_ids_for_user(self, user_id: int) -> list[int]:
        """返回用户可访问的知识库 ID 列表：包含角色授权 + 用户自己创建的知识库。"""
        # 1. 通过角色授权（KBRoleAccess）访问的知识库
        role_stmt = (
            select(KBRoleAccess.kb_id)
            .join(UserRole, KBRoleAccess.role_id == UserRole.role_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id, Role.status == "active")
            .distinct()
        )
        role_based = list(self.db.scalars(role_stmt).all())

        # 2. 用户自己创建的知识库（创建即可访问）
        owned_stmt = select(KnowledgeBase.id).where(KnowledgeBase.user_id == user_id)
        owned = list(self.db.scalars(owned_stmt).all())

        return list(set(role_based + owned))

    def get_kb_access_map(self, kb_ids: list[int]) -> dict[int, list[int]]:
        if not kb_ids:
            return {}
        stmt = select(KBRoleAccess).where(KBRoleAccess.kb_id.in_(kb_ids))
        rows = list(self.db.scalars(stmt).all())
        result: dict[int, list[int]] = {kb_id: [] for kb_id in kb_ids}
        for row in rows:
            result[row.kb_id].append(row.role_id)
        return result


def get_accessible_kb_ids(db: Session, user_id: int) -> list[int]:
    """获取用户可访问的知识库 ID 列表（含自己创建 + 角色授权），优先从 Redis 缓存读取。

    这是跨服务层/API 层的唯一权威实现，避免重复逻辑。
    """
    from repositories.redis_repo import redis_repo

    cache_key = f"kb_access:{user_id}"
    cached = redis_repo.get_list(cache_key)
    if cached is not None:
        return [int(x) for x in cached]
    kb_ids = sorted(set(KBAccessRepo(db).get_accessible_kb_ids_for_user(user_id)))
    redis_repo.set_list(cache_key, kb_ids, expire_seconds=KB_ACCESS_CACHE_TTL)
    return kb_ids
