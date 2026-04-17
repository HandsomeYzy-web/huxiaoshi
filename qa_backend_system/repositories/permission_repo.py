from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.entities.permission import Permission


class PermissionRepo:
    def __init__(self, db: Session):
        self.db = db

    def upsert_permission(
        self,
        code: str,
        name: str,
        description: str | None,
        module: str,
        parent_code: str | None = None,
        icon: str | None = None,
        path: str | None = None,
        type: str = "feature",
        status: str = "active",
        sort: int = 0,
    ) -> Permission:
        permission = self.db.get(Permission, code)
        if permission:
            permission.name = name
            permission.description = description
            permission.parent_code = parent_code
            permission.module = module
            permission.icon = icon
            permission.path = path
            permission.type = type
            permission.status = status
            permission.sort = sort
        else:
            permission = Permission(
                code=code,
                name=name,
                description=description,
                parent_code=parent_code,
                module=module,
                icon=icon,
                path=path,
                type=type,
                status=status,
                sort=sort,
            )
            self.db.add(permission)
        self.db.commit()
        self.db.refresh(permission)
        return permission

    def list_permissions(self) -> list[Permission]:
        stmt = select(Permission).order_by(Permission.module, Permission.sort, Permission.code)
        return list(self.db.scalars(stmt).all())

    def get_permission(self, code: str) -> Optional[Permission]:
        return self.db.get(Permission, code)

    def delete_permission(self, code: str) -> bool:
        permission = self.get_permission(code)
        if not permission:
            return False
        self.db.delete(permission)
        self.db.commit()
        return True
