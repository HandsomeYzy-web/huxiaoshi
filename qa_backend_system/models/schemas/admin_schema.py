from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    code: str = Field(..., max_length=64)
    name: str = Field(..., max_length=64)
    description: Optional[str] = Field(None, max_length=256)


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    description: Optional[str] = Field(None, max_length=256)
    status: Optional[str] = Field(None, max_length=16)


class RoleResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    role_type: str
    status: str
    created_at: datetime
    permissions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PermissionCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=256)
    parent_code: Optional[str] = Field(None, max_length=64)
    module: str = Field(..., min_length=1, max_length=32)
    icon: Optional[str] = Field(None, max_length=64)
    path: Optional[str] = Field(None, max_length=255)
    type: str = Field(default="feature", max_length=16)
    status: str = Field(default="active", max_length=16)
    sort: int = Field(default=0, ge=0)


class PermissionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=256)
    parent_code: Optional[str] = Field(None, max_length=64)
    module: Optional[str] = Field(None, min_length=1, max_length=32)
    icon: Optional[str] = Field(None, max_length=64)
    path: Optional[str] = Field(None, max_length=255)
    type: Optional[str] = Field(None, max_length=16)
    status: Optional[str] = Field(None, max_length=16)
    sort: Optional[int] = Field(None, ge=0)


class PermissionResponse(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    parent_code: Optional[str] = None
    module: str
    icon: Optional[str] = None
    path: Optional[str] = None
    type: str
    status: str
    sort: int

    model_config = ConfigDict(from_attributes=True)


class PermissionTreeNode(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    parent_code: Optional[str] = None
    module: str
    icon: Optional[str] = None
    path: Optional[str] = None
    type: str = "feature"
    status: str = "active"
    sort: int = 0
    children: list["PermissionTreeNode"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class UserRoleAssign(BaseModel):
    role_ids: list[int] = Field(default_factory=list)


class RolePermissionSet(BaseModel):
    permission_codes: list[str] = Field(default_factory=list)


class KBAccessSet(BaseModel):
    role_ids: list[int] = Field(default_factory=list)


class KBAccessResponse(BaseModel):
    kb_id: int
    accessible_role_ids: list[int]


class UserAdminResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime
    roles: list[RoleResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


PermissionTreeNode.model_rebuild()
