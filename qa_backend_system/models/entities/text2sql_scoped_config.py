from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Text2SQLScopedConfig(Base):
    """按「用户 + 连接」隔离的 Text2SQL 配置（当前主用配置表）。

    存储某用户在某连接下选了哪些表（selected_tables，JSON）与自定义 prompt（prompt_hint）；
    (user_id, connection_key) 唯一，切换连接互不影响。
    """

    __tablename__ = "text2sql_scoped_config"
    __table_args__ = (
        UniqueConstraint("user_id", "connection_key", name="uq_t2s_scoped_config_user_conn"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    connection_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    selected_tables: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

