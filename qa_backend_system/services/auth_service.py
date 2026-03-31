from sqlalchemy.orm import Session

from core.exceptions import AuthenticationError, DuplicateResourceError
from core.security import create_access_token, get_password_hash, verify_password
from models.entities.user import User
from models.schemas.auth_schema import LoginRequest, RegisterRequest, TokenResponse, UserInfo
from repositories.user_repo import UserRepo


class AuthService:
    def register(self, db: Session, request: RegisterRequest) -> UserInfo:
        repo = UserRepo(db)
        if repo.get_by_username(request.username):
            raise DuplicateResourceError("用户名已存在")
        if repo.get_by_email(request.email):
            raise DuplicateResourceError("邮箱已被注册")
        user = User(
            username=request.username,
            email=str(request.email),
            hashed_password=get_password_hash(request.password),
        )
        created = repo.create_user(user)
        return UserInfo.model_validate(created)

    def login(self, db: Session, request: LoginRequest) -> TokenResponse:
        repo = UserRepo(db)
        user = repo.get_by_username(request.username)
        if not user or not verify_password(request.password, user.hashed_password):
            raise AuthenticationError("用户名或密码错误")
        if not user.is_active:
            raise AuthenticationError("账号已被禁用")
        token = create_access_token(user.id)
        return TokenResponse(access_token=token)


auth_service = AuthService()
