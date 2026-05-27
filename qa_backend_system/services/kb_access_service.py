from sqlalchemy.orm import Session

from core.exceptions import ResourceNotFoundError
from repositories.kb_access_repo import KBAccessRepo
from repositories.kb_repo import KBRepo
from repositories.role_repo import RoleRepo


class KBAccessService:
    """知识库授权管理服务（仅供管理员使用）。
    用户侧访问权限查询已统一由 api.dependencies.get_accessible_kb_ids 处理。
    """

    def set_kb_access(self, db: Session, kb_id: int, role_ids: list[int]) -> None:
        role_repo = RoleRepo(db)
        for role_id in role_ids:
            if not role_repo.get_role_by_id(role_id):
                raise ResourceNotFoundError(f"Role {role_id} not found")
        KBAccessRepo(db).set_kb_role_access(kb_id, role_ids)

    def get_kb_access(self, db: Session, kb_id: int) -> list[int]:
        return KBAccessRepo(db).get_kb_accessible_role_ids(kb_id)

    def get_all_kb_access(self, db: Session) -> list[dict]:
        kbs = KBRepo(db).get_all_kbs()
        access_map = KBAccessRepo(db).get_kb_access_map([kb.id for kb in kbs])
        return [{"kb_id": kb_id, "accessible_role_ids": role_ids} for kb_id, role_ids in access_map.items()]


kb_access_service = KBAccessService()
