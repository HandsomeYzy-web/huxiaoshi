# 将所有实体在这里暴露，方便 core/database.py 获取 metadata 进行统一建表
from .base import Base
from .chat_message import ChatMessage
from .chat_session import ChatSession
from .document_chunk import DocumentChunk
from .knowledge_base import KnowledgeBase
from .knowledge_file import KnowledgeFile
from .model_config import ModelConfig
from .text2sql_config import Text2SQLConfig
from .text2sql_connection import Text2SQLConnection
from .text2sql_field_permission import Text2SQLFieldPermission
from .text2sql_query_log import Text2SQLQueryLog
from .text2sql_scoped_config import Text2SQLScopedConfig
from .text2sql_table_relation import Text2SQLTableRelation

__all__ = [
    "Base", "KnowledgeBase", "KnowledgeFile", "DocumentChunk",
    "ChatSession", "ChatMessage", "ModelConfig",
    "Text2SQLConfig", "Text2SQLConnection", "Text2SQLFieldPermission",
    "Text2SQLQueryLog", "Text2SQLScopedConfig", "Text2SQLTableRelation",
]
