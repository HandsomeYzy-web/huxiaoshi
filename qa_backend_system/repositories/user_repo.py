"""用户仓储层：提供 User（用户）的数据库增删改查操作，支持按用户名、邮箱、ID 查询。"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.entities.user import User


class UserRepo:
    def __init__(self, db: Session):
        self.db = db

    def get_by_username(self, username: str) -> Optional[User]:
        stmt = select(User).where(User.username == username)
        return self.db.scalars(stmt).first()

    def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        return self.db.scalars(stmt).first()

    def get_by_id(self, user_id: int) -> Optional[User]:
        stmt = select(User).where(User.id == user_id)
        return self.db.scalars(stmt).first()

    def create_user(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
