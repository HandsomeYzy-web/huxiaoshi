"""
Embedding 单例服务：统一管理 OpenAIEmbeddings 实例的获取和初始化。

使用 langchain_openai.OpenAIEmbeddings，兼容任意 OpenAI 兼容的
Embedding API（dashscope、ollama、jina 等）。
The vector dimension is auto-detected on first use by embedding a probe text.
"""
from __future__ import annotations

import threading

from langchain_openai import OpenAIEmbeddings

from core.connection_password_cipher import secret_cipher
from core.logger import logger
from core.url_utils import normalize_embedding_base_url

_instance: OpenAIEmbeddings | None = None
_lock = threading.Lock()
_vector_dim: int | None = None


def _normalize_api_base(url: str) -> str:
    """Normalize API base URL for OpenAI-compatible endpoints.

    Delegates to the shared normalize_embedding_base_url utility.
    """
    return normalize_embedding_base_url(url)


def _resolve_embedding_config() -> tuple[str, str, str] | None:
    """Return (api_base, api_key, model) from DB active config."""
    try:
        from core.database import SessionLocal
        from repositories.model_config_repo import ModelConfigRepo
        db = SessionLocal()
        try:
            active = ModelConfigRepo(db).get_active("embedding")
            if active:
                return active.api_base_url, secret_cipher.decrypt(active.api_key), active.model_name
        finally:
            db.close()
    except Exception:
        pass
    return None


def _detect_vector_dim(embeddings: OpenAIEmbeddings) -> int:
    """Embed a short probe text to auto-detect the vector dimension."""
    try:
        vec = embeddings.embed_query("dimension probe")
        dim = len(vec)
        logger.info(f"Auto-detected embedding vector dimension: {dim}")
        return dim
    except Exception as e:
        logger.error(f"Failed to auto-detect embedding dimension: {e}")
        raise RuntimeError(f"无法自动检测 Embedding 维度，请检查模型配置: {e}") from e


def get_embedding_vector_dim() -> int:
    """Return vector dimension (auto-detected on first call)."""
    global _vector_dim
    if _vector_dim is None:
        # This will also initialize _instance if needed
        emb = get_embeddings()
        with _lock:
            if _vector_dim is None:
                _vector_dim = _detect_vector_dim(emb)
    return _vector_dim


def get_embeddings() -> OpenAIEmbeddings:
    """Return the global embeddings instance (lazy-initialized thread-safe singleton)."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                cfg = _resolve_embedding_config()
                if cfg is None:
                    raise RuntimeError(
                        "Embedding 模型未配置，请在管理面板中添加并激活一个 Embedding 模型配置"
                    )
                api_base, api_key, model = cfg
                normalized_base = _normalize_api_base(api_base)
                logger.info(
                    f"Initializing embedding model: {model}, "
                    f"api_base: {normalized_base}"
                )
                _instance = OpenAIEmbeddings(
                    openai_api_base=normalized_base,
                    openai_api_key=api_key,
                    model=model,
                    request_timeout=60,
                    # ── 兼容性参数 ──
                    # 禁用 tiktoken 分词: 许多非 OpenAI API (ollama, vllm,
                    # dashscope, local 模型等) 不支持 token IDs 输入，
                    # 设为 False 后 langchain 会直接发送原始文本。
                    check_embedding_ctx_length=False,
                )
    return _instance


def reset_embeddings() -> None:
    """Reset cached instance and dimension (called when active embedding config changes)."""
    global _instance, _vector_dim
    with _lock:
        _instance = None
        _vector_dim = None

