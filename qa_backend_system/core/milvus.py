import threading

from pymilvus import connections

from core.config import settings

# TODO:移入setting
DEFAULT_MILVUS_ALIAS = "default"

_milvus_lock = threading.Lock()


def ensure_milvus_connection(alias: str = DEFAULT_MILVUS_ALIAS) -> str:
    """Ensure a usable pymilvus ORM connection exists for the given alias (thread-safe)."""
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
