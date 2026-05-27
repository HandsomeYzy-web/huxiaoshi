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


@router.post("/register", response_model=UnifiedResponse[UserInfo], summary="Register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    return success(data=auth_service.register(db, request), message="Registered")


@router.post("/login", response_model=UnifiedResponse[TokenResponse], summary="Login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    return success(data=auth_service.login(db, request), message="Logged in")


@router.get("/me", response_model=UnifiedResponse[UserInfo], summary="Current user")
async def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return success(data=auth_service.get_me(db, current_user), message="Fetched current user")
