from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class KBRoleAccess(Base):
    __tablename__ = "kb_role_access"

    kb_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_base.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )

    role: Mapped["Role"] = relationship("Role", back_populates="kb_accesses")
