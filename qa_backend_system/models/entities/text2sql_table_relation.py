from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Text2SQLTableRelation(Base):
    """表间 JOIN 关系白名单（支持复合键），多表查询只能按本表登记的关系 JOIN。

    source_columns / target_columns 以 JSON 存列名数组；*_columns_hash 是列集合的哈希，
    与表名一起构成唯一约束，用于高效去重；is_active 控制该关系是否参与路由与校验。
    """

    __tablename__ = "text2sql_table_relation"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "connection_key",
            "source_table",
            "target_table",
            "source_columns_hash",
            "target_columns_hash",
            name="uq_t2s_relation_user_conn_pair_cols",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    connection_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_table: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_columns: Mapped[str] = mapped_column(Text, nullable=False)
    source_columns_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_table: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_columns: Mapped[str] = mapped_column(Text, nullable=False)
    target_columns_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(16), nullable=False, default="N:1")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

