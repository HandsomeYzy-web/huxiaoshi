"""
Milvus 向量数据库连接管理模块：提供线程安全的 Milvus 连接初始化与复用。
"""

import threading

from pymilvus import connections

from core.config import settings

# Milvus 默认连接别名
DEFAULT_MILVUS_ALIAS = "default"

# 线程锁，确保多线程环境下只初始化一次 Milvus 连接
_milvus_lock = threading.Lock()


def ensure_milvus_connection(alias: str = DEFAULT_MILVUS_ALIAS) -> str:
    """确保指定别名的 pymilvus ORM 连接已存在（双重检查锁，线程安全）。"""
    if not connections.has_connection(alias):
        with _milvus_lock:
            # Double-check after acquiring lock
            if not connections.has_connection(alias):
                connections.connect(
                    alias=alias,
                    host=settings.MILVUS_HOST,
                    port=settings.MILVUS_PORT,
                )
    return alias
