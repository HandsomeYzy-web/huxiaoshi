from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


from .base import Base


class ModelConfig(Base):
    __tablename__ = "model_config"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    model_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="模型类型")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, comment="模型供应商")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="显示名称")
    model_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="模型标识")
    api_base_url: Mapped[str] = mapped_column(String(512), nullable=False, comment="API Base URL")
    api_key: Mapped[str] = mapped_column(String(512), nullable=False, comment="API Key")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否激活")
    extra_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="额外参数(JSON)")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
