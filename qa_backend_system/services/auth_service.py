from sqlalchemy.orm import Session

from core.exceptions import AuthenticationError, DuplicateResourceError
from core.security import create_access_token, get_password_hash, verify_password
from models.entities.user import User
from models.schemas.auth_schema import LoginRequest, RegisterRequest, TokenResponse, UserInfo
from repositories.user_repo import UserRepo
from services.role_service import role_service


class AuthService:
    def register(self, db: Session, request: RegisterRequest) -> UserInfo:
        repo = UserRepo(db)
        if repo.get_by_username(request.username):
            raise DuplicateResourceError("Username already exists")
        if repo.get_by_email(str(request.email)):
            raise DuplicateResourceError("Email already exists")
        user = User(
            username=request.username,
            email=str(request.email),
            hashed_password=get_password_hash(request.password),
        )
        created = repo.create_user(user)
        # TODO：这一步失败是否原子性无法保证
        role_service.ensure_default_role(db, created.id)
        # TODO：检查为什么注册要返回用户权限，有必要返回吗
        user_info = UserInfo.model_validate(created)
        user_info.permissions = sorted(role_service.get_user_permissions(db, created.id))
        user_info.roles = role_service.get_user_role_names(db, created.id)
        return user_info

    def login(self, db: Session, request: LoginRequest) -> TokenResponse:
        repo = UserRepo(db)
        user = repo.get_by_username(request.username)
        if not user or not verify_password(request.password, user.hashed_password):
            raise AuthenticationError("Invalid username or password")
        if not user.is_active:
            raise AuthenticationError("Account is disabled")
        return TokenResponse(access_token=create_access_token(user.id))


auth_service = AuthService()
