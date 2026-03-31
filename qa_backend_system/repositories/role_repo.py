from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.orm import Session, selectinload

from models.entities.role import Role, UserRole, Permission, RolePermission, KBRoleAccess


class RoleRepo:
    def __init__(self, db: Session):
        self.db = db

    # ─── Role CRUD ────────────────────────────────────────────────

    def create_role(self, role: Role) -> Role:
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role

    def get_role_by_id(self, role_id: int) -> Optional[Role]:
        return self.db.get(Role, role_id)

    def get_role_by_name(self, name: str) -> Optional[Role]:
        return self.db.scalars(select(Role).where(Role.name == name)).first()

    def list_roles(self) -> list[Role]:
        return list(self.db.scalars(select(Role).order_by(Role.id)).all())

    def update_role(self, role_id: int, name: str, description: str) -> Optional[Role]:
        role = self.get_role_by_id(role_id)
        if not role:
            return None
        role.name = name
        role.description = description
        self.db.commit()
        self.db.refresh(role)
        return role

    def delete_role(self, role_id: int) -> bool:
        role = self.get_role_by_id(role_id)
        if not role or role.is_system:
            return False
        self.db.delete(role)
        self.db.commit()
        return True

    # ─── UserRole ─────────────────────────────────────────────────

    def assign_role(self, user_id: int, role_id: int) -> None:
        existing = self.db.get(UserRole, (user_id, role_id))
        if not existing:
            self.db.add(UserRole(user_id=user_id, role_id=role_id))
            self.db.commit()

    def remove_role(self, user_id: int, role_id: int) -> None:
        stmt = delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        self.db.execute(stmt)
        self.db.commit()

    def get_user_roles(self, user_id: int) -> list[Role]:
        stmt = (
            select(Role)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
        )
        return list(self.db.scalars(stmt).all())

    def get_users_by_role(self, role_id: int) -> list[int]:
        """返回拥有该角色的所有 user_id"""
        stmt = select(UserRole.user_id).where(UserRole.role_id == role_id)
        return list(self.db.scalars(stmt).all())

    def set_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        """覆盖更新用户角色列表"""
        stmt = delete(UserRole).where(UserRole.user_id == user_id)
        self.db.execute(stmt)
        for rid in role_ids:
            self.db.add(UserRole(user_id=user_id, role_id=rid))
        self.db.commit()

    # ─── Permission ───────────────────────────────────────────────

    def upsert_permission(self, code: str, name: str, description: str, module: str) -> Permission:
        perm = self.db.get(Permission, code)
        if perm:
            perm.name = name
            perm.description = description
            perm.module = module
        else:
            perm = Permission(code=code, name=name, description=description, module=module)
            self.db.add(perm)
        self.db.commit()
        return perm

    def list_permissions(self) -> list[Permission]:
        return list(self.db.scalars(select(Permission).order_by(Permission.module, Permission.code)).all())

    # ─── RolePermission ───────────────────────────────────────────

    def get_role_permission_codes(self, role_id: int) -> set[str]:
        stmt = select(RolePermission.permission_code).where(RolePermission.role_id == role_id)
        return set(self.db.scalars(stmt).all())

    def set_role_permissions(self, role_id: int, permission_codes: list[str]) -> None:
        """覆盖更新角色权限"""
        stmt = delete(RolePermission).where(RolePermission.role_id == role_id)
        self.db.execute(stmt)
        for code in permission_codes:
            self.db.add(RolePermission(role_id=role_id, permission_code=code))
        self.db.commit()

    def get_user_permission_codes(self, user_id: int) -> set[str]:
        """获取用户基于角色的所有权限code集合"""
        stmt = (
            select(RolePermission.permission_code)
            .join(UserRole, RolePermission.role_id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
        )
        return set(self.db.scalars(stmt).all())

    # ─── KBRoleAccess ─────────────────────────────────────────────

    def set_kb_role_access(self, kb_id: int, role_ids: list[int]) -> None:
        """覆盖更新某知识库可被哪些角色访问"""
        stmt = delete(KBRoleAccess).where(KBRoleAccess.kb_id == kb_id)
        self.db.execute(stmt)
        for rid in role_ids:
            self.db.add(KBRoleAccess(kb_id=kb_id, role_id=rid))
        self.db.commit()

    def get_kb_accessible_role_ids(self, kb_id: int) -> list[int]:
        stmt = select(KBRoleAccess.role_id).where(KBRoleAccess.kb_id == kb_id)
        return list(self.db.scalars(stmt).all())

    def get_accessible_kb_ids_for_user(self, user_id: int) -> list[int]:
        """获取用户（基于其角色）可访问的所有 kb_id"""
        stmt = (
            select(KBRoleAccess.kb_id)
            .join(UserRole, KBRoleAccess.role_id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .distinct()
        )
        return list(self.db.scalars(stmt).all())

    def get_kb_access_map(self, kb_ids: list[int]) -> dict[int, list[int]]:
        """批量获取多个KB的可访问角色ID，返回 {kb_id: [role_id, ...]}"""
        if not kb_ids:
            return {}
        stmt = select(KBRoleAccess).where(KBRoleAccess.kb_id.in_(kb_ids))
        rows = list(self.db.scalars(stmt).all())
        result: dict[int, list[int]] = {kid: [] for kid in kb_ids}
        for row in rows:
            result[row.kb_id].append(row.role_id)
        return result
