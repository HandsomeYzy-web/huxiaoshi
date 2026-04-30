from sqlalchemy import select
from sqlalchemy.orm import Session

from core.exceptions import DuplicateResourceError, PermissionDeniedError, ResourceNotFoundError
from core.logger import logger
from core.permissions import ALL_PERMISSIONS, DEFAULT_ROLE_SEEDS, DEFAULT_USER_ROLE_CODE
from models.entities.role import Role
from models.entities.user import User
from models.schemas.admin_schema import RoleCreate, RoleUpdate
from repositories.permission_repo import PermissionRepo
from repositories.role_repo import RoleRepo
from repositories.user_repo import UserRepo


class RoleService:
    def init_defaults(self, db: Session) -> None:
        role_repo = RoleRepo(db)
        permission_repo = PermissionRepo(db)

        parent_codes = {permission.parent_code for permission in ALL_PERMISSIONS if permission.parent_code}
        roots = [permission for permission in ALL_PERMISSIONS if permission.parent_code is None]
        children = [
            permission
            for permission in ALL_PERMISSIONS
            if permission.parent_code and permission.parent_code not in parent_codes
        ]
        mid_level = [
            permission
            for permission in ALL_PERMISSIONS
            if permission.parent_code and permission.parent_code in {root.code for root in roots}
        ]
        leaves = [
            permission
            for permission in ALL_PERMISSIONS
            if permission.parent_code and permission not in mid_level and permission not in roots
        ]

        for permission in roots + mid_level + leaves:
            permission_repo.upsert_permission(
                code=permission.code,
                name=permission.name,
                description=permission.description,
                parent_code=permission.parent_code,
                module=permission.module,
                icon=permission.icon,
                path=permission.path,
                type=permission.type,
                status=permission.status,
                sort=permission.sort,
            )

        for seed in DEFAULT_ROLE_SEEDS:
            role = role_repo.get_role_by_code(seed.code)
            if not role:
                role = role_repo.create_role(
                    Role(
                        code=seed.code,
                        name=seed.name,
                        description=seed.description,
                        role_type=seed.role_type,
                        status=seed.status,
                    )
                )
            else:
                role.name = seed.name
                role.description = seed.description
                role.role_type = seed.role_type
                role.status = seed.status
                db.commit()
                db.refresh(role)
            role_repo.set_role_permissions(role.id, list(seed.permissions))

        logger.info("Permission defaults initialized")

    def ensure_default_role(self, db: Session, user_id: int) -> None:
        repo = RoleRepo(db)
        default_role = repo.get_role_by_code(DEFAULT_USER_ROLE_CODE)
        if not default_role:
            raise ResourceNotFoundError("Default user role is missing")
        repo.assign_role(user_id, default_role.id)
    # TODO：检查这里有没有返回permissions的必要
    def list_roles(self, db: Session) -> list[dict]:
        repo = RoleRepo(db)
        result = []
        for role in repo.list_roles():
            result.append(
                {
                    "id": role.id,
                    "code": role.code,
                    "name": role.name,
                    "description": role.description,
                    "role_type": role.role_type,
                    "status": role.status,
                    "created_at": role.created_at,
                    "permissions": sorted(repo.get_role_permission_codes(role.id)),
                }
            )
        return result
    # TODO:同上
    def create_role(self, db: Session, req: RoleCreate) -> dict:
        repo = RoleRepo(db)
        if repo.get_role_by_code(req.code):
            raise DuplicateResourceError(f"Role code '{req.code}' already exists")
        if repo.get_role_by_name(req.name):
            raise DuplicateResourceError(f"Role '{req.name}' already exists")
        role = repo.create_role(
            Role(
                code=req.code,
                name=req.name,
                description=req.description,
                role_type="custom",
                status="active",
            )
        )
        return {
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "role_type": role.role_type,
            "status": role.status,
            "created_at": role.created_at,
            "permissions": [],
        }

    # TODO:同上
    def update_role(self, db: Session, role_id: int, req: RoleUpdate) -> dict:
        repo = RoleRepo(db)
        role = repo.get_role_by_id(role_id)
        if not role:
            raise ResourceNotFoundError(f"Role {role_id} not found")
        if role.role_type == "system" and req.status == "disabled":
            raise PermissionDeniedError("System role cannot be disabled")
        if req.name:
            existing = repo.get_role_by_name(req.name)
            if existing and existing.id != role_id:
                raise DuplicateResourceError(f"Role '{req.name}' already exists")
        updated = repo.update_role(
            role_id,
            name=req.name,
            description=req.description if "description" in req.model_fields_set else role.description,
            status=req.status,
        )
        return {
            "id": updated.id,
            "code": updated.code,
            "name": updated.name,
            "description": updated.description,
            "role_type": updated.role_type,
            "status": updated.status,
            "created_at": updated.created_at,
            "permissions": sorted(repo.get_role_permission_codes(updated.id)),
        }
    # #TODO: 检查删除role时，role_permission和user_role是否也被删除，同时保证原子性
    def delete_role(self, db: Session, role_id: int) -> None:
        repo = RoleRepo(db)
        role = repo.get_role_by_id(role_id)
        if not role:
            raise ResourceNotFoundError(f"Role {role_id} not found")
        if role.role_type == "system":
            raise PermissionDeniedError("System role cannot be deleted")
        repo.delete_role(role_id)

    def set_role_permissions(self, db: Session, role_id: int, permission_codes: list[str]) -> None:
        role_repo = RoleRepo(db)
        permission_repo = PermissionRepo(db)
        role = role_repo.get_role_by_id(role_id)
        if not role:
            raise ResourceNotFoundError(f"Role {role_id} not found")
        invalid = [code for code in permission_codes if not permission_repo.get_permission(code)]
        if invalid:
            raise ResourceNotFoundError(f"Invalid permissions: {invalid}")
        role_repo.set_role_permissions(role_id, permission_codes)
    # TODO:新建user——service并移入
    def list_users(self, db: Session) -> list[dict]:
        # TODO:这一行代码越权了，应该封装在user_repo中
        users = list(db.scalars(select(User).order_by(User.id)).all())
        repo = RoleRepo(db)
        result = []
        for user in users:
            roles = []
            for role in repo.get_user_roles(user.id):
                roles.append(
                    {
                        "id": role.id,
                        "code": role.code,
                        "name": role.name,
                        "description": role.description,
                        "role_type": role.role_type,
                        "status": role.status,
                        "created_at": role.created_at,
                        # TODO：检查这里有没有返回permissions的必要
                        "permissions": sorted(repo.get_role_permission_codes(role.id)),
                    }
                )
            result.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_active": user.is_active,
                    "created_at": user.created_at,
                    "roles": roles,
                }
            )
        return result
    # TODO:同上
    def set_user_roles(self, db: Session, user_id: int, role_ids: list[int], assigned_by: int | None = None) -> None:
        user_repo = UserRepo(db)
        repo = RoleRepo(db)
        if not user_repo.get_by_id(user_id):
            raise ResourceNotFoundError(f"User {user_id} not found")
        for role_id in role_ids:
            role = repo.get_role_by_id(role_id)
            if not role:
                raise ResourceNotFoundError(f"Role {role_id} not found")
            if role.status != "active":
                raise PermissionDeniedError(f"Role {role.name} is disabled")
        repo.set_user_roles(user_id, role_ids, assigned_by=assigned_by)

    # TODO:同上
    def get_user_permissions(self, db: Session, user_id: int) -> set[str]:
        user = UserRepo(db).get_by_id(user_id)
        if not user:
            return set()
        return RoleRepo(db).get_user_permission_codes(user_id)

    # TODO:同上
    def get_user_role_names(self, db: Session, user_id: int) -> list[str]:
        return RoleRepo(db).get_user_role_names(user_id)


role_service = RoleService()
