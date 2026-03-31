from datetime import datetime
from typing import List

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Role(Base):
    """角色表 — 定义系统中的角色（如：管理员、普通用户、访客）"""
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="角色名称")
    description: Mapped[str] = mapped_column(String(256), nullable=True, comment="角色描述")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否为内置系统角色")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # 关联
    user_roles: Mapped[List["UserRole"]] = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions: Mapped[List["RolePermission"]] = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    kb_accesses: Mapped[List["KBRoleAccess"]] = relationship("KBRoleAccess", back_populates="role", cascade="all, delete-orphan")


class UserRole(Base):
    """用户-角色关联表（多对多）"""
    __tablename__ = "user_role"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")


class Permission(Base):
    """权限定义表 — 系统中所有可分配的功能权限"""
    __tablename__ = "permission"

    # code 是权限唯一标识，如 "kb.manage"、"chat.use"、"admin.roles"
    code: Mapped[str] = mapped_column(String(64), primary_key=True, comment="权限代码（主键）")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="权限名称")
    description: Mapped[str] = mapped_column(String(256), nullable=True, comment="权限描述")
    module: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="所属模块")

    role_permissions: Mapped[List["RolePermission"]] = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class RolePermission(Base):
    """角色-权限关联表（多对多）"""
    __tablename__ = "role_permission"

    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(String(64), ForeignKey("permission.code", ondelete="CASCADE"), primary_key=True)

    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="role_permissions")


class KBRoleAccess(Base):
    """知识库-角色访问控制表 — 决定哪些角色可以检索哪个知识库"""
    __tablename__ = "kb_role_access"

    kb_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_base.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True)

    role: Mapped["Role"] = relationship("Role", back_populates="kb_accesses")
