"""安全工具模块：提供密码哈希、密码验证、JWT 令牌生成与解码功能。"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from core.config import settings


def _to_bytes(password: str) -> bytes:
    """使用 SHA-256 预处理密码：规避 bcrypt 72 字节上限，同时支持任意长度密码。"""
    return hashlib.sha256(password.encode("utf-8")).digest()


def get_password_hash(password: str) -> str:
    """对明文密码进行 bcrypt 哈希加密，返回哈希字符串。"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(_to_bytes(password), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希值是否匹配。"""
    return bcrypt.checkpw(_to_bytes(plain_password), hashed_password.encode("utf-8"))


def create_access_token(subject: int) -> str:
    """根据用户 ID 生成 JWT 访问令牌，包含过期时间。"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    """解码 JWT 令牌，返回用户 ID；令牌无效或过期时返回 None。"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None
