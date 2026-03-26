# 将所有实体在这里暴露，方便 core/database.py 获取 metadata 进行统一建表
from .base import Base
from .knowledge_base import KnowledgeBase
from .knowledge_file import KnowledgeFile

__all__ = ["Base", "KnowledgeBase", "KnowledgeFile"]