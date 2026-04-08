from sqlalchemy.orm import Session

from core.exceptions import DuplicateResourceError, PermissionDeniedError, ResourceNotFoundError
from core.logger import logger
from core.permissions import ADMIN_PERMISSIONS, ALL_PERMISSIONS, DEFAULT_USER_PERMISSIONS
from models.entities.role import Role
from models.entities.user import User
from models.schemas.admin_schema import RoleCreate, RoleUpdate
from repositories.role_repo import RoleRepo
from repositories.user_repo import UserRepo


class RoleService:

    # ─── 初始化 ───────────────────────────────────────────────────

    def init_defaults(self, db: Session) -> None:
        """应用启动时调用，确保默认权限、角色已存在"""
        repo = RoleRepo(db)

        # 1. 同步所有权限定义到数据库
        for perm in ALL_PERMISSIONS:
            repo.upsert_permission(perm.code, perm.name, perm.description, perm.module)

        # 2. 确保系统角色存在
        admin_role = repo.get_role_by_name("admin")
        if not admin_role:
            admin_role = repo.create_role(Role(name="admin", description="系统管理员，拥有全部权限", is_system=True))
        repo.set_role_permissions(admin_role.id, ADMIN_PERMISSIONS)

        user_role = repo.get_role_by_name("user")
        if not user_role:
            user_role = repo.create_role(Role(name="user", description="普通用户", is_system=True))
        repo.set_role_permissions(user_role.id, DEFAULT_USER_PERMISSIONS)

        logger.info("权限系统初始化完成")

    # ─── 角色 CRUD ────────────────────────────────────────────────

    def list_roles(self, db: Session) -> list[dict]:
        repo = RoleRepo(db)
        roles = repo.list_roles()
        result = []
        for r in roles:
            perms = repo.get_role_permission_codes(r.id)
            result.append({
                "id": r.id, "name": r.name, "description": r.description,
                "is_system": r.is_system, "created_at": r.created_at, "permissions": list(perms)
            })
        return result

    def create_role(self, db: Session, req: RoleCreate) -> dict:
        repo = RoleRepo(db)
        if repo.get_role_by_name(req.name):
            raise DuplicateResourceError(f"角色名称 '{req.name}' 已存在")
        role = repo.create_role(Role(name=req.name, description=req.description, is_system=False))
        return {"id": role.id, "name": role.name, "description": role.description,
                "is_system": role.is_system, "created_at": role.created_at, "permissions": []}

    def update_role(self, db: Session, role_id: int, req: RoleUpdate) -> dict:
        repo = RoleRepo(db)
        role = repo.get_role_by_id(role_id)
        if not role:
            raise ResourceNotFoundError(f"角色 ID={role_id} 不存在")
        if role.is_system:
            raise PermissionDeniedError("系统内置角色不允许修改名称")
        existing = repo.get_role_by_name(req.name)
        if existing and existing.id != role_id:
            raise DuplicateResourceError(f"角色名称 '{req.name}' 已存在")
        updated = repo.update_role(role_id, req.name, req.description or "")
        perms = repo.get_role_permission_codes(role_id)
        return {"id": updated.id, "name": updated.name, "description": updated.description,
                "is_system": updated.is_system, "created_at": updated.created_at, "permissions": list(perms)}

    def delete_role(self, db: Session, role_id: int) -> None:
        repo = RoleRepo(db)
        role = repo.get_role_by_id(role_id)
        if not role:
            raise ResourceNotFoundError(f"角色 ID={role_id} 不存在")
        if role.is_system:
            raise PermissionDeniedError("系统内置角色不允许删除")
        repo.delete_role(role_id)

    def set_role_permissions(self, db: Session, role_id: int, permission_codes: list[str]) -> None:
        repo = RoleRepo(db)
        if not repo.get_role_by_id(role_id):
            raise ResourceNotFoundError(f"角色 ID={role_id} 不存在")
        # 校验权限code是否存在
        all_codes = {p.code for p in ALL_PERMISSIONS}
        invalid = [c for c in permission_codes if c not in all_codes]
        if invalid:
            raise ResourceNotFoundError(f"无效的权限代码: {invalid}")
        repo.set_role_permissions(role_id, permission_codes)

    # ─── 用户管理 ─────────────────────────────────────────────────

    def list_users(self, db: Session) -> list[dict]:
        from sqlalchemy import select
        users = list(db.scalars(select(User).order_by(User.id)).all())
        repo = RoleRepo(db)
        result = []
        for u in users:
            roles = repo.get_user_roles(u.id)
            role_list = []
            for r in roles:
                perms = repo.get_role_permission_codes(r.id)
                role_list.append({"id": r.id, "name": r.name, "description": r.description,
                                   "is_system": r.is_system, "created_at": r.created_at, "permissions": list(perms)})
            result.append({
                "id": u.id, "username": u.username, "email": u.email,
                "is_active": u.is_active, "is_admin": u.is_admin,
                "created_at": u.created_at, "roles": role_list
            })
        return result

    def set_user_roles(self, db: Session, user_id: int, role_ids: list[int]) -> None:
        user_repo = UserRepo(db)
        role_repo = RoleRepo(db)
        if not user_repo.get_by_id(user_id):
            raise ResourceNotFoundError(f"用户 ID={user_id} 不存在")
        for rid in role_ids:
            if not role_repo.get_role_by_id(rid):
                raise ResourceNotFoundError(f"角色 ID={rid} 不存在")
        role_repo.set_user_roles(user_id, role_ids)

    def set_user_admin(self, db: Session, user_id: int, is_admin: bool) -> None:
        user_repo = UserRepo(db)
        user = user_repo.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"用户 ID={user_id} 不存在")
        user.is_admin = is_admin
        db.commit()

    # ─── 知识库访问控制 ─────────────────────────────────────────────

    def set_kb_access(self, db: Session, kb_id: int, role_ids: list[int]) -> None:
        repo = RoleRepo(db)
        for rid in role_ids:
            if not repo.get_role_by_id(rid):
                raise ResourceNotFoundError(f"角色 ID={rid} 不存在")
        repo.set_kb_role_access(kb_id, role_ids)

    def get_kb_access(self, db: Session, kb_id: int) -> list[int]:
        return RoleRepo(db).get_kb_accessible_role_ids(kb_id)

    # ─── 权限查询 ─────────────────────────────────────────────────

    def get_user_permissions(self, db: Session, user_id: int) -> set[str]:
        """管理员拥有全部权限，普通用户基于角色"""
        from repositories.user_repo import UserRepo as UR
        user = UR(db).get_by_id(user_id)
        if not user:
            return set()
        if user.is_admin:
            return set(ADMIN_PERMISSIONS)
        return RoleRepo(db).get_user_permission_codes(user_id)

    def can_access_kb(self, db: Session, user_id: int, kb_id: int) -> bool:
        """判断用户是否有权访问（检索）某知识库"""
        from repositories.user_repo import UserRepo as UR
        user = UR(db).get_by_id(user_id)
        if not user:
            return False
        if user.is_admin:
            return True
        # 先检查用户有 kb.query 权限
        perms = RoleRepo(db).get_user_permission_codes(user_id)
        if "kb.query" not in perms:
            return False
        # 再检查知识库访问控制
        accessible_kb_ids = RoleRepo(db).get_accessible_kb_ids_for_user(user_id)
        return kb_id in accessible_kb_ids

    def get_accessible_kb_ids(self, db: Session, user_id: int) -> list[int] | None:
        """返回用户可访问的kb_id列表，None表示管理员无限制"""
        from repositories.user_repo import UserRepo as UR
        user = UR(db).get_by_id(user_id)
        if not user:
            return []
        if user.is_admin:
            return None  # None 表示不做限制
        return RoleRepo(db).get_accessible_kb_ids_for_user(user_id)


role_service = RoleService()
