"""
Reranker Service — 对召回结果进行精排。

支持两种模式：
1. OpenAI 兼容接口（/v1/rerank）— 常见于 Jina、Cohere、本地 infinity-emb 等
2. 降级到向量分数（当 RERANKER_ENABLED=False 或接口不可用时直接返回原排序）
"""
from __future__ import annotations

import httpx

from core.exceptions import ExternalServiceError
from core.logger import logger
from core.url_utils import normalize_rerank_base_url


class RerankerService:
    """调用外部 Reranker API，返回重新排序后的 (原始index, score) 列表。"""

    def _resolve_reranker_config(self) -> tuple[bool, str, str, str]:
        """Return (enabled, base_url, api_key, model) from DB."""
        try:
            from core.database import SessionLocal
            from repositories.model_config_repo import ModelConfigRepo
            db = SessionLocal()
            try:
                active = ModelConfigRepo(db).get_active("rerank")
                if active:
                    return True, active.api_base_url, active.api_key, active.model_name
            finally:
                db.close()
        except Exception:
            pass
        return False, "", "", ""

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        """
        对 documents 列表按照与 query 的相关性进行精排。

        Returns:
            list of (original_index, rerank_score), sorted descending by score,
            limited to top_k items.
        """
        try:
            enabled, base_url, api_key, model = self._resolve_reranker_config()
            if not enabled or not base_url:
                return [(i, 1.0 / (i + 1)) for i in range(min(top_k, len(documents)))]
            return self._call_rerank_api(query, documents, top_k, base_url, api_key, model)
        except ExternalServiceError:
            raise
        except Exception as exc:
            logger.error(f"Reranker 调用异常: {exc}")
            raise ExternalServiceError(f"Reranker 服务不可用: {exc}") from exc

    def _call_rerank_api(
        self,
        query: str,
        documents: list[str],
        top_k: int,
        base_url: str,
        api_key: str,
        model: str,
    ) -> list[tuple[int, float]]:
        """向符合 Jina/Cohere 规范的 /v1/rerank 端点发请求。"""
        url = normalize_rerank_base_url(base_url) + "/v1/rerank"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "query": query,
            "documents": documents,
            "top_n": top_k,
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=payload, headers=headers)

        if resp.status_code != 200:
            raise ExternalServiceError(
                f"Reranker API 返回错误: status={resp.status_code}, body={resp.text[:200]}"
            )

        data = resp.json()
        results = data.get("results", [])
        ranked: list[tuple[int, float]] = [
            (int(item["index"]), float(item["relevance_score"]))
            for item in results
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


reranker_service = RerankerService()
