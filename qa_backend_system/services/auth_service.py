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
        role_service.ensure_default_role(db, created.id)

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

    def get_me(self, db: Session, current_user: User) -> UserInfo:
        """获取当前用户信息，包含权限列表、角色列表和权限树。"""
        from services.permission_service import permission_service

        user_info = UserInfo.model_validate(current_user)
        user_perms = role_service.get_user_permissions(db, current_user.id)
        user_info.permissions = sorted(user_perms)
        user_info.roles = role_service.get_user_role_names(db, current_user.id)
        user_info.permission_tree = permission_service.build_permission_tree(db, user_perms)
        return user_info


auth_service = AuthService()
