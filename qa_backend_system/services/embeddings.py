"""
Shared embeddings singleton.

Both QAService and RAGService previously created their own CustomE5Embeddings
instances with identical config. This module exposes a single lazy-initialized
instance so the HTTP client and model handle are reused across the process.
"""
from __future__ import annotations

from core.config import settings
from services.custom_e5_embeddings import CustomE5Embeddings

_instance: CustomE5Embeddings | None = None


def get_embeddings() -> CustomE5Embeddings:
    """Return the global embeddings instance (lazy-initialized singleton)."""
    global _instance
    if _instance is None:
        _instance = CustomE5Embeddings(
            api_base=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
            model=settings.EMBEDDING_MODEL,
        )
    return _instance

