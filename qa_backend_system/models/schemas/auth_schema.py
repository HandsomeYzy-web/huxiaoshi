"""认证模块数据模型：包含用户注册、登录、令牌响应、用户信息等接口模型。"""

from typing import List
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_]+$", description="用户名，仅允许字母/数字/下划线")
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(..., min_length=6, max_length=128, description="密码，至少6位")


class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool = False
    permissions: List[str] = Field(default_factory=list, description="用户拥有的权限code列表")

    model_config = ConfigDict(from_attributes=True)

