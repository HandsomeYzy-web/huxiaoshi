"""数据库实体基类模块：定义 SQLAlchemy ORM 的声明式基类。"""

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """所有 SQLAlchemy ORM 模型的基类，所有实体类必须继承此类。"""
    pass