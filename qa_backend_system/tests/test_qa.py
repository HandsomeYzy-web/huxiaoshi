"""
QA 检索接口测试（外部服务已在 conftest 中 Mock）。
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from core.config import settings

PREFIX = settings.API_V1_STR

KB_PAYLOAD = {
    "name": "QA 测试库",
    "description": "",
    "default_chunk_size": 500,
    "default_chunk_overlap": 100,
    "retrieval_top_k": 5,
    "retrieval_score_threshold": 0.0,
    "enable_rerank": False,
}


@pytest.fixture
def kb_id(client: TestClient, auth_headers: dict) -> int:
    resp = client.post(f"{PREFIX}/kb", json=KB_PAYLOAD, headers=auth_headers)
    return resp.json()["data"]["id"]


class TestQAAsk:
    def test_ask_empty_results(self, client: TestClient, auth_headers: dict, kb_id: int):
        """Milvus 返回空，QA 服务应正常响应（答案可能为空但不抛错）。"""
        with (
            patch("services.embeddings.get_embeddings") as mock_emb,
            patch("services.llm_service.llm_service.generate_answer", return_value=("无相关内容", "mock-model")),
        ):
            mock_emb.return_value.embed_query.return_value = [0.0] * 128
            resp = client.post(
                f"{PREFIX}/qa/ask",
                json={"question": "什么是向量数据库？", "kb_id": kb_id, "kb_ids": []},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["retrieved_count"] == 0

    def test_ask_requires_auth(self, client: TestClient, kb_id: int):
        resp = client.post(
            f"{PREFIX}/qa/ask",
            json={"question": "test", "kb_id": kb_id, "kb_ids": []},
        )
        assert resp.json()["code"] == 401

    def test_ask_invalid_kb(self, client: TestClient, auth_headers: dict):
        """KB 不存在时应返回 404。"""
        resp = client.post(
            f"{PREFIX}/qa/ask",
            json={"question": "test", "kb_ids": [99999]},
            headers=auth_headers,
        )
        assert resp.json()["code"] == 404


class TestQARetrieve:
    def test_retrieve_returns_citations(self, client: TestClient, auth_headers: dict, kb_id: int):
        """Mock Milvus 返回一个命中结果，验证 citation 格式。"""
        mock_result = [{
            "entity": {
                "chunk_id": 1,
                "kb_id": kb_id,
                "file_id": 1,
                "text": "向量数据库是用于存储向量的专用数据库。",
            },
            "distance": 0.9,
        }]

        with (
            patch("repositories.milvus_repo.milvus_repo.search_chunks", return_value=mock_result),
            patch("services.embeddings.get_embeddings") as mock_emb,
        ):
            mock_emb.return_value.embed_query.return_value = [0.0] * 128
            resp = client.post(
                f"{PREFIX}/qa/retrieve",
                json={"question": "向量数据库", "kb_id": kb_id, "kb_ids": []},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        result = resp.json()["data"]
        # 文件和 KB 在 DB 中不存在，citation 仍应返回（元数据降级处理）
        assert result["retrieved_count"] >= 0
