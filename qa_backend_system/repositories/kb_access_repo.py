from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models.entities.kb_role_access import KBRoleAccess
from models.entities.role import Role
from models.entities.user_role import UserRole


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
        stmt = (
            select(KBRoleAccess.kb_id)
            .join(UserRole, KBRoleAccess.role_id == UserRole.role_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id, Role.status == "active")
            .distinct()
        )
        return list(self.db.scalars(stmt).all())

    def get_kb_access_map(self, kb_ids: list[int]) -> dict[int, list[int]]:
        if not kb_ids:
            return {}
        stmt = select(KBRoleAccess).where(KBRoleAccess.kb_id.in_(kb_ids))
        rows = list(self.db.scalars(stmt).all())
        result: dict[int, list[int]] = {kb_id: [] for kb_id in kb_ids}
        for row in rows:
            result[row.kb_id].append(row.role_id)
        return result
