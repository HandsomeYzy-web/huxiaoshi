# 将所有实体在这里暴露，方便 core/database.py 获取 metadata 进行统一建表
from .base import Base
from .chat_message import ChatMessage
from .chat_session import ChatSession
from .document_chunk import DocumentChunk
from .knowledge_base import KnowledgeBase
from .knowledge_file import KnowledgeFile
from .model_config import ModelConfig
from .user import User
from .role import Role, UserRole, Permission, RolePermission, KBRoleAccess

__all__ = [
    "Base", "KnowledgeBase", "KnowledgeFile", "DocumentChunk",
    "ChatSession", "ChatMessage", "User", "ModelConfig",
    "Role", "UserRole", "Permission", "RolePermission", "KBRoleAccess",
]

