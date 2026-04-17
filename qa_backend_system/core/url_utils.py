"""URL 归一化工具：确保各类模型 API 的 base_url 只保留根地址，避免路径重复拼接。"""
from __future__ import annotations

import re


def normalize_llm_base_url(url: str) -> str:
    """去掉 LLM 常见尾部路径，只保留根地址。

    ChatOpenAI 会自动拼接 /chat/completions，因此必须剥掉：
      - /chat/completions
      - /chat
      - /completions
    """
    url = url.strip().rstrip("/")
    # 从长到短依次剥离
    for suffix in ("/chat/completions", "/chat", "/completions"):
        if url.lower().endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url.rstrip("/")


def normalize_embedding_base_url(url: str) -> str:
    """去掉 Embedding 尾部 /embeddings，langchain 会自动追加。"""
    url = url.strip().rstrip("/")
    if url.lower().endswith("/embeddings"):
        url = url[: -len("/embeddings")]
    return url.rstrip("/")


def normalize_rerank_base_url(url: str) -> str:
    """去掉 Reranker 尾部路径。

    常见结尾：
      - /v1/rerank
      - /rerank
    代码层会自行拼接 /v1/rerank。
    """
    url = url.strip().rstrip("/")
    for suffix in ("/v1/rerank", "/rerank"):
        if url.lower().endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url.rstrip("/")
