from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_current_user
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.auth_schema import LoginRequest, RegisterRequest, TokenResponse, UserInfo
from services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UnifiedResponse[UserInfo], summary="注册新用户")
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    return success(data=auth_service.register(db, request), message="注册成功")


@router.post("/login", response_model=UnifiedResponse[TokenResponse], summary="用户登录")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    return success(data=auth_service.login(db, request), message="登录成功")


@router.get("/me", response_model=UnifiedResponse[UserInfo], summary="获取当前用户信息（含权限列表）")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from services.role_service import role_service
    perms = role_service.get_user_permissions(db, current_user.id)
    user_data = UserInfo.model_validate(current_user)
    user_data.permissions = list(perms)
    return success(data=user_data, message="获取用户信息成功")

