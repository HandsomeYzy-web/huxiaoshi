from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Text2SQLConfig(Base):
    """旧版全局 Text2SQL 配置表（仅按用户隔离，未区分连接；保留用于向后兼容）。

    新逻辑请用 Text2SQLScopedConfig（按「用户 + 连接」隔离），本表仅在 scoped 配置缺失时回退读取。
    """

    __tablename__ = "text2sql_config"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
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

