from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Text2SQLConnection(Base):
    """Text2SQL「被查询业务库」的连接配置（全局当前生效的外部库连接）。

    password 字段存放的是 ConnectionPasswordCipher 加密后的密文（带 enc:v1: 前缀），非明文。
    """

    __tablename__ = "text2sql_connection"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    db_type: Mapped[str] = mapped_column(String(32), nullable=False, default="mysql")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=3306)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password: Mapped[str] = mapped_column(String(1024), nullable=False)  # 加密后的密文，非明文
    database: Mapped[str] = mapped_column(String(255), nullable=False)
    charset: Mapped[str] = mapped_column(String(64), nullable=False, default="utf8mb4")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

