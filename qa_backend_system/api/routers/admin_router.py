"""
管理员专属接口：
  - 角色 CRUD & 权限配置
  - 用户管理（列表、角色分配、设为管理员）
  - 知识库访问控制（决定哪些角色可检索哪个KB）
  - 权限列表查询
"""
from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session
from typing import List

from api.dependencies import require_admin, get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.admin_schema import (
    RoleCreate, RoleUpdate, RoleResponse, PermissionResponse,
    UserRoleAssign, RolePermissionSet, KBAccessSet, KBAccessResponse, UserAdminResponse,
)
from services.role_service import role_service

router = APIRouter(prefix="/admin", tags=["Admin"])


# ─── 权限列表 ─────────────────────────────────────────────────

@router.get(
    "/permissions",
    response_model=UnifiedResponse[List[PermissionResponse]],
    summary="获取系统所有可用权限",
)
async def list_permissions(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    from repositories.role_repo import RoleRepo
    perms = RoleRepo(db).list_permissions()
    return success(data=perms, message="获取成功")


# ─── 角色管理 ─────────────────────────────────────────────────

@router.get(
    "/roles",
    response_model=UnifiedResponse[List[RoleResponse]],
    summary="获取所有角色列表",
)
async def list_roles(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return success(data=role_service.list_roles(db), message="获取成功")


@router.post(
    "/roles",
    response_model=UnifiedResponse[RoleResponse],
    summary="创建新角色",
)
async def create_role(
    req: RoleCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return success(data=role_service.create_role(db, req), message="角色创建成功")


@router.put(
    "/roles/{role_id}",
    response_model=UnifiedResponse[RoleResponse],
    summary="更新角色基本信息",
)
async def update_role(
    req: RoleUpdate,
    role_id: int = Path(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return success(data=role_service.update_role(db, role_id, req), message="角色更新成功")


@router.delete(
    "/roles/{role_id}",
    response_model=UnifiedResponse[None],
    summary="删除角色（系统角色不可删除）",
)
async def delete_role(
    role_id: int = Path(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    role_service.delete_role(db, role_id)
    return success(data=None, message="角色删除成功")


@router.put(
    "/roles/{role_id}/permissions",
    response_model=UnifiedResponse[None],
    summary="设置角色权限（覆盖更新）",
)
async def set_role_permissions(
    req: RolePermissionSet,
    role_id: int = Path(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    role_service.set_role_permissions(db, role_id, req.permission_codes)
    return success(data=None, message="角色权限设置成功")


# ─── 用户管理 ─────────────────────────────────────────────────

@router.get(
    "/users",
    response_model=UnifiedResponse[List[UserAdminResponse]],
    summary="获取所有用户列表（含角色信息）",
)
async def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return success(data=role_service.list_users(db), message="获取成功")


@router.put(
    "/users/{user_id}/roles",
    response_model=UnifiedResponse[None],
    summary="设置用户角色（覆盖更新）",
)
async def set_user_roles(
    req: UserRoleAssign,
    user_id: int = Path(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    role_service.set_user_roles(db, user_id, req.role_ids)
    return success(data=None, message="用户角色设置成功")


@router.put(
    "/users/{user_id}/admin",
    response_model=UnifiedResponse[None],
    summary="设置/取消用户管理员状态",
)
async def set_user_admin(
    user_id: int = Path(...),
    is_admin: bool = True,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    role_service.set_user_admin(db, user_id, is_admin)
    return success(data=None, message=f"{'设置' if is_admin else '取消'}管理员成功")


# ─── 知识库访问控制 ─────────────────────────────────────────────

@router.put(
    "/kb/{kb_id}/access",
    response_model=UnifiedResponse[None],
    summary="设置知识库可见角色（覆盖更新）",
)
async def set_kb_access(
    req: KBAccessSet,
    kb_id: int = Path(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    role_service.set_kb_access(db, kb_id, req.role_ids)
    return success(data=None, message="知识库访问控制设置成功")


@router.get(
    "/kb/{kb_id}/access",
    response_model=UnifiedResponse[KBAccessResponse],
    summary="查看知识库可见角色列表",
)
async def get_kb_access(
    kb_id: int = Path(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    role_ids = role_service.get_kb_access(db, kb_id)
    return success(data={"kb_id": kb_id, "accessible_role_ids": role_ids}, message="获取成功")


@router.get(
    "/kb/access/all",
    response_model=UnifiedResponse[List[KBAccessResponse]],
    summary="批量获取所有知识库的访问控制配置",
)
async def get_all_kb_access(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    from repositories.kb_repo import KBRepo
    from repositories.role_repo import RoleRepo
    kbs = KBRepo(db).get_all_kbs()
    kb_ids = [kb.id for kb in kbs]
    access_map = RoleRepo(db).get_kb_access_map(kb_ids)
    result = [{"kb_id": kid, "accessible_role_ids": rids} for kid, rids in access_map.items()]
    return success(data=result, message="获取成功")


# ─── 模型配置管理 ─────────────────────────────────────────────

from models.schemas.model_schema import (
    ModelConfigCreate,
    ModelConfigUpdate,
    ModelConfigResponse,
    ModelProviderInfo,
    ModelActivateRequest,
    ModelActivateResponse,
)
from services.model_config_service import model_config_service


@router.get(
    "/models",
    response_model=UnifiedResponse[List[ModelConfigResponse]],
    summary="获取模型配置列表",
)
async def list_model_configs(
    model_type: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return success(data=model_config_service.list_configs(db, model_type), message="获取成功")


@router.get(
    "/models/providers",
    response_model=UnifiedResponse[List[ModelProviderInfo]],
    summary="获取支持的模型供应商列表",
)
async def list_model_providers(
    _admin: User = Depends(require_admin),
):
    return success(data=model_config_service.get_providers_info(), message="获取成功")


@router.get(
    "/models/{config_id}",
    response_model=UnifiedResponse[ModelConfigResponse],
    summary="获取单个模型配置详情",
)
async def get_model_config(
    config_id: int = Path(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return success(data=model_config_service.get_config(db, config_id), message="获取成功")


@router.post(
    "/models",
    response_model=UnifiedResponse[ModelConfigResponse],
    summary="创建模型配置",
)
async def create_model_config(
    req: ModelConfigCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return success(data=model_config_service.create_config(db, req), message="模型配置创建成功")


@router.put(
    "/models/{config_id}",
    response_model=UnifiedResponse[ModelConfigResponse],
    summary="更新模型配置",
)
async def update_model_config(
    req: ModelConfigUpdate,
    config_id: int = Path(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return success(data=model_config_service.update_config(db, config_id, req), message="模型配置更新成功")


@router.post(
    "/models/{config_id}/activate",
    response_model=UnifiedResponse[ModelActivateResponse],
    summary="激活指定模型配置（同类型只能激活一个）",
)
async def activate_model_config(
    config_id: int = Path(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = model_config_service.activate_config(db, config_id)
    msg = "模型已激活"
    if result["warning"]:
        msg = result["warning"]
    return success(data=result, message=msg)


@router.delete(
    "/models/{config_id}",
    response_model=UnifiedResponse[None],
    summary="删除模型配置（激活状态不可删除）",
)
async def delete_model_config(
    config_id: int = Path(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    model_config_service.delete_config(db, config_id)
    return success(data=None, message="模型配置已删除")


@router.post(
    "/models/rebuild-all-kbs",
    response_model=UnifiedResponse[dict],
    summary="重建所有知识库向量（Embedding 模型切换后使用）",
)
async def rebuild_all_knowledge_bases(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = model_config_service.rebuild_all_knowledge_bases(db)
    return success(
        data=result,
        message=f"已提交重建任务：{result['total_kbs']} 个知识库，{result['total_files']} 个文件排队处理中",
    )
