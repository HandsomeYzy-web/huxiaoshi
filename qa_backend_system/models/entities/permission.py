from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Permission(Base):
    __tablename__ = "permission"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    parent_code: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("permission.code", ondelete="CASCADE"), nullable=True, index=True
    )
    module: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    icon: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="feature", index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    parent: Mapped[Optional["Permission"]] = relationship(
        "Permission", remote_side=[code], foreign_keys=[parent_code]
    )
    role_permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )
