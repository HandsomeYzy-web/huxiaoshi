from sqlalchemy.orm import Session

from core.exceptions import ResourceNotFoundError
from repositories.kb_access_repo import KBAccessRepo
from repositories.kb_repo import KBRepo
from repositories.role_repo import RoleRepo
from repositories.user_repo import UserRepo


class KBAccessService:
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
    
    # TODO： 重构这个函数和下面的函数，以及其下游调用链，之后采用role控制kb访问权限，用户只能通过角色获得访问权限，不再区分拥有和被授权的知识库
    def can_access_kb(self, db: Session, user_id: int, kb_id: int) -> bool:
        user = UserRepo(db).get_by_id(user_id)
        if not user:
            return False
        return kb_id in self.get_accessible_kb_ids(db, user_id)

    def get_accessible_kb_ids(self, db: Session, user_id: int) -> list[int]:
        user = UserRepo(db).get_by_id(user_id)
        if not user:
            return []
        owned_ids = [kb.id for kb in KBRepo(db).get_all_kbs(user_id=user_id)]
        role_ids = KBAccessRepo(db).get_accessible_kb_ids_for_user(user_id)
        return sorted(set(owned_ids + role_ids))


kb_access_service = KBAccessService()
