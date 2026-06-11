"""数据库连接密码对称加解密工具（Text2SQL 业务库密码落库前后的安全边界）。

基于 Fernet（AES-128-CBC + HMAC）对连接密码做对称加解密：
- 密钥来源优先级：FERNET_KEY 直接使用；否则用 APP_SECRET_KEY 派生；
- 密文统一带 "enc:v1:" 前缀作为版本标识；
- decrypt 对「无前缀」的历史明文行做向后兼容（直接原样返回），便于平滑迁移旧数据。
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings

# 密文前缀（版本标识）：用于区分「已加密」与「历史明文」，也为日后密钥/算法升级预留空间。
_ENCRYPTED_PREFIX = "enc:v1:"


def _derive_fernet_key_from_app_secret(app_secret_key: str) -> bytes:
    """由应用密钥派生 Fernet 密钥：SHA-256 摘要后做 urlsafe base64 编码（满足 Fernet 32 字节要求）。"""
    digest = hashlib.sha256(app_secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _build_fernet() -> Fernet | None:
    """按优先级构建 Fernet 实例：显式 FERNET_KEY 优先，其次由应用密钥派生；都缺失则返回 None。"""
    raw_fernet_key = str(settings.FERNET_KEY or "").strip()
    if raw_fernet_key:
        return Fernet(raw_fernet_key.encode("utf-8"))

    app_secret_key = str(settings.APP_SECRET_KEY or "").strip()
    if app_secret_key:
        return Fernet(_derive_fernet_key_from_app_secret(app_secret_key))
    return None


class ConnectionPasswordCipher:
    """连接密码加解密器：构造时确定密钥，缺失密钥时加解密会显式报错。"""

    def __init__(self):
        self._fernet = _build_fernet()

    def encrypt(self, plaintext: str) -> str:
        """加密明文密码，返回带版本前缀的密文；空串原样返回；无密钥时报错。"""
        if not plaintext:
            return ""
        if self._fernet is None:
            raise ValueError("FERNET_KEY/APP_SECRET_KEY is required for encryption")
        token = self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return f"{_ENCRYPTED_PREFIX}{token}"

    def decrypt(self, ciphertext_or_plaintext: str) -> str:
        """解密密码：带前缀的走解密；无前缀视为历史明文直接返回；空串返回空；token 损坏则报错。"""
        raw = str(ciphertext_or_plaintext or "").strip()
        if not raw:
            return ""

        if not raw.startswith(_ENCRYPTED_PREFIX):
            # 向后兼容：历史明文行没有前缀，直接原样返回（便于旧数据平滑迁移）。
            return raw

        if self._fernet is None:
            raise ValueError("FERNET_KEY/APP_SECRET_KEY is required for decryption")
        token = raw[len(_ENCRYPTED_PREFIX):]
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Failed to decrypt connection password, check FERNET_KEY/APP_SECRET_KEY") from exc


# 进程内共享实例：Fernet 无状态、线程安全，可并发复用，避免各调用方重复构建。
# 除 Text2SQL 连接密码外，模型配置 API Key 等敏感字段的落库加解密也复用它。
secret_cipher = ConnectionPasswordCipher()
