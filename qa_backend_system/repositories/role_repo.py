from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models.entities.role import Role
from models.entities.role_permission import RolePermission
from models.entities.user_role import UserRole


class RoleRepo:
    def __init__(self, db: Session):
        self.db = db

    def create_role(self, role: Role) -> Role:
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role

    def get_role_by_id(self, role_id: int) -> Optional[Role]:
        return self.db.get(Role, role_id)

    def get_role_by_name(self, name: str) -> Optional[Role]:
        return self.db.scalars(select(Role).where(Role.name == name)).first()

    def get_role_by_code(self, code: str) -> Optional[Role]:
        return self.db.scalars(select(Role).where(Role.code == code)).first()

    def list_roles(self) -> list[Role]:
        return list(self.db.scalars(select(Role).order_by(Role.id)).all())

    def update_role(
        self,
        role_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> Optional[Role]:
        role = self.get_role_by_id(role_id)
        if not role:
            return None
        if name is not None:
            role.name = name
        if description is not None or description is None:
            role.description = description
        if status is not None:
            role.status = status
        self.db.commit()
        self.db.refresh(role)
        return role

    def delete_role(self, role_id: int) -> bool:
        role = self.get_role_by_id(role_id)
        if not role or role.role_type == "system":
            return False
        self.db.delete(role)
        self.db.commit()
        return True

    def assign_role(self, user_id: int, role_id: int, assigned_by: int | None = None) -> None:
        if not self.db.get(UserRole, (user_id, role_id)):
            self.db.add(UserRole(user_id=user_id, role_id=role_id, assigned_by=assigned_by))
            self.db.commit()

    def set_user_roles(self, user_id: int, role_ids: list[int], assigned_by: int | None = None) -> None:
        self.db.execute(delete(UserRole).where(UserRole.user_id == user_id))
        for role_id in role_ids:
            self.db.add(UserRole(user_id=user_id, role_id=role_id, assigned_by=assigned_by))
        self.db.commit()

    def get_user_roles(self, user_id: int) -> list[Role]:
        stmt = select(Role).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == user_id)
        return list(self.db.scalars(stmt).all())

    def get_user_role_names(self, user_id: int) -> list[str]:
        stmt = select(Role.name).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == user_id)
        return list(self.db.scalars(stmt).all())

    def get_role_permission_codes(self, role_id: int) -> set[str]:
        stmt = select(RolePermission.permission_code).where(RolePermission.role_id == role_id)
        return set(self.db.scalars(stmt).all())

    def set_role_permissions(self, role_id: int, permission_codes: list[str]) -> None:
        self.db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for code in permission_codes:
            self.db.add(RolePermission(role_id=role_id, permission_code=code))
        self.db.commit()

    def get_user_permission_codes(self, user_id: int) -> set[str]:
        stmt = (
            select(RolePermission.permission_code)
            .join(UserRole, RolePermission.role_id == UserRole.role_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id, Role.status == "active")
        )
        return set(self.db.scalars(stmt).all())
