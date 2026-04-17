from sqlalchemy.orm import Session

from core.exceptions import DuplicateResourceError, ResourceNotFoundError
from core.permissions import SUPER_ADMIN_ROLE_CODE
from models.entities.permission import Permission
from models.schemas.admin_schema import PermissionCreate, PermissionTreeNode, PermissionUpdate
from repositories.permission_repo import PermissionRepo
from repositories.role_repo import RoleRepo


class PermissionService:
    def list_permissions(self, db: Session, module: str | None = None) -> list:
        items = PermissionRepo(db).list_permissions()
        if module is not None:
            items = [item for item in items if item.module == module]
        return items

    def get_permission(self, db: Session, code: str):
        permission = PermissionRepo(db).get_permission(code)
        if not permission:
            raise ResourceNotFoundError(f"Permission '{code}' not found")
        return permission

    def create_permission(self, db: Session, req: PermissionCreate):
        permission_repo = PermissionRepo(db)
        role_repo = RoleRepo(db)
        if permission_repo.get_permission(req.code):
            raise DuplicateResourceError(f"Permission '{req.code}' already exists")
        if req.parent_code and not permission_repo.get_permission(req.parent_code):
            raise ResourceNotFoundError(f"Parent permission '{req.parent_code}' not found")
        permission = permission_repo.upsert_permission(**req.model_dump())
        super_admin_role = role_repo.get_role_by_code(SUPER_ADMIN_ROLE_CODE)
        if super_admin_role:
            permission_codes = sorted(role_repo.get_role_permission_codes(super_admin_role.id) | {permission.code})
            role_repo.set_role_permissions(super_admin_role.id, permission_codes)
        return permission

    def update_permission(self, db: Session, code: str, req: PermissionUpdate):
        permission_repo = PermissionRepo(db)
        permission = permission_repo.get_permission(code)
        if not permission:
            raise ResourceNotFoundError(f"Permission '{code}' not found")
        payload = req.model_dump(exclude_unset=True)
        if "parent_code" in payload and payload["parent_code"] and not permission_repo.get_permission(payload["parent_code"]):
            raise ResourceNotFoundError(f"Parent permission '{payload['parent_code']}' not found")
        merged = {
            "code": permission.code,
            "name": payload.get("name", permission.name),
            "description": payload.get("description", permission.description),
            "parent_code": payload.get("parent_code", permission.parent_code),
            "module": payload.get("module", permission.module),
            "icon": payload.get("icon", permission.icon),
            "path": payload.get("path", permission.path),
            "type": payload.get("type", permission.type),
            "status": payload.get("status", permission.status),
            "sort": payload.get("sort", permission.sort),
        }
        return permission_repo.upsert_permission(**merged)

    def delete_permission(self, db: Session, code: str) -> None:
        if not PermissionRepo(db).delete_permission(code):
            raise ResourceNotFoundError(f"Permission '{code}' not found")

    def build_permission_tree(self, db: Session, permission_codes: set[str] | None = None) -> list[dict]:
        all_perms = PermissionRepo(db).list_permissions()
        if permission_codes is not None:
            all_perms = [p for p in all_perms if p.code in permission_codes and p.status == "active"]

        perm_map: dict[str, dict] = {}
        for p in all_perms:
            perm_map[p.code] = PermissionTreeNode(
                code=p.code,
                name=p.name,
                description=p.description,
                parent_code=p.parent_code,
                module=p.module,
                icon=p.icon,
                path=p.path,
                type=p.type,
                status=p.status,
                sort=p.sort,
                children=[],
            ).model_dump()

        roots: list[dict] = []
        for code, node in perm_map.items():
            parent = node["parent_code"]
            if parent and parent in perm_map:
                perm_map[parent]["children"].append(node)
            else:
                roots.append(node)

        def sort_tree(nodes: list[dict]) -> list[dict]:
            nodes.sort(key=lambda n: (n["sort"], n["code"]))
            for n in nodes:
                sort_tree(n["children"])
            return nodes

        return sort_tree(roots)

    def build_full_tree(self, db: Session) -> list[dict]:
        return self.build_permission_tree(db, permission_codes=None)


permission_service = PermissionService()
