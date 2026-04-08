from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ─── 角色 ─────────────────────────────────────────────────────

class RoleCreate(BaseModel):
    name: str = Field(..., max_length=64, description="角色名称")
    description: str | None = Field(None, max_length=256, description="角色描述")


class RoleUpdate(BaseModel):
    name: str = Field(..., max_length=64)
    description: str | None = Field(None, max_length=256)


class RoleResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_system: bool
    created_at: datetime
    permissions: list[str] = Field(default_factory=list, description="权限code列表")

    model_config = ConfigDict(from_attributes=True)


# ─── 权限 ─────────────────────────────────────────────────────

class PermissionResponse(BaseModel):
    code: str
    name: str
    description: str | None = None
    module: str

    model_config = ConfigDict(from_attributes=True)


# ─── 用户-角色 ────────────────────────────────────────────────

class UserRoleAssign(BaseModel):
    role_ids: list[int] = Field(..., description="要分配给用户的角色ID列表（覆盖更新）")


class RolePermissionSet(BaseModel):
    permission_codes: list[str] = Field(..., description="要分配给角色的权限code列表（覆盖更新）")


# ─── 知识库访问控制 ─────────────────────────────────────────────

class KBAccessSet(BaseModel):
    role_ids: list[int] = Field(..., description="可访问该知识库的角色ID列表（覆盖更新）")


class KBAccessResponse(BaseModel):
    kb_id: int
    accessible_role_ids: list[int]


# ─── 管理员用户列表 ────────────────────────────────────────────

class UserAdminResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    roles: list[RoleResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
