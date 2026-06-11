from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Text2SQLFieldPermission(Base):
    """Text2SQL 字段级查询开关（按「用户 + 连接 + 表 + 列」唯一）。

    query_enabled=False 表示该列不可被查询。注意「默认放开」语义由服务层实现：
    没有对应记录的列视为可查，本表只显式记录被关闭/调整过的列。
    """

    __tablename__ = "text2sql_field_permission"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "connection_key",
            "table_name",
            "column_name",
            name="uq_t2s_field_perm_user_conn_table_col",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    connection_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    column_name: Mapped[str] = mapped_column(String(64), nullable=False)
    query_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

