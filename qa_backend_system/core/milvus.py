from pymilvus import connections

from core.config import settings


DEFAULT_MILVUS_ALIAS = "default"


def ensure_milvus_connection(alias: str = DEFAULT_MILVUS_ALIAS) -> str:
    """Ensure a usable pymilvus ORM connection exists for the given alias."""
    if not connections.has_connection(alias):
        connections.connect(
            alias=alias,
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
        )
    return alias
