from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_current_user
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.auth_schema import LoginRequest, RegisterRequest, TokenResponse, UserInfo
from services.auth_service import auth_service
from services.permission_service import permission_service
from services.role_service import role_service

router = APIRouter(prefix="/auth", tags=["Auth"])

# TODO:这里只有success是否合理
@router.post("/register", response_model=UnifiedResponse[UserInfo], summary="Register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    return success(data=auth_service.register(db, request), message="Registered")


@router.post("/login", response_model=UnifiedResponse[TokenResponse], summary="Login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    return success(data=auth_service.login(db, request), message="Logged in")


@router.get("/me", response_model=UnifiedResponse[UserInfo], summary="Current user")
async def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # TODO:为什么不写进service里
    user_data = UserInfo.model_validate(current_user)
    user_perms = role_service.get_user_permissions(db, current_user.id)
    user_data.permissions = sorted(user_perms)
    user_data.roles = role_service.get_user_role_names(db, current_user.id)
    user_data.permission_tree = permission_service.build_permission_tree(db, user_perms)
    return success(data=user_data, message="Fetched current user")
