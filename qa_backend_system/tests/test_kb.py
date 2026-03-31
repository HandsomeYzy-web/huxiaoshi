"""
知识库 CRUD 接口测试。
"""
import pytest
from fastapi.testclient import TestClient

from core.config import settings

PREFIX = settings.API_V1_STR


@pytest.fixture
def kb_payload():
    return {
        "name": "测试知识库",
        "description": "用于单测",
        "default_chunk_size": 500,
        "default_chunk_overlap": 100,
        "retrieval_top_k": 3,
        "retrieval_score_threshold": 0.0,
        "enable_rerank": False,
    }


class TestKBCreate:
    def test_create_success(self, client: TestClient, auth_headers: dict, kb_payload: dict):
        resp = client.post(f"{PREFIX}/kb", json=kb_payload, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == kb_payload["name"]
        assert data["retrieval_top_k"] == 3
        assert data["enable_rerank"] is False

    def test_create_requires_auth(self, client: TestClient, kb_payload: dict):
        resp = client.post(f"{PREFIX}/kb", json=kb_payload)
        assert resp.status_code == 200
        assert resp.json()["code"] == 401

    def test_create_missing_name(self, client: TestClient, auth_headers: dict):
        resp = client.post(f"{PREFIX}/kb", json={"description": "no name"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 422


class TestKBList:
    def test_list_empty(self, client: TestClient, auth_headers: dict):
        resp = client.get(f"{PREFIX}/kb", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_returns_own_kbs_only(self, client: TestClient, kb_payload: dict):
        from tests.conftest import register_and_login
        token_a = register_and_login(client, "user_a", "Pass@1234")
        token_b = register_and_login(client, "user_b", "Pass@1234")

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        client.post(f"{PREFIX}/kb", json=kb_payload, headers=headers_a)

        resp_a = client.get(f"{PREFIX}/kb", headers=headers_a)
        resp_b = client.get(f"{PREFIX}/kb", headers=headers_b)
        assert len(resp_a.json()["data"]) == 1
        assert len(resp_b.json()["data"]) == 0


class TestKBUpdate:
    def test_update_retrieval_config(self, client: TestClient, auth_headers: dict, kb_payload: dict):
        create_resp = client.post(f"{PREFIX}/kb", json=kb_payload, headers=auth_headers)
        kb_id = create_resp.json()["data"]["id"]

        update_resp = client.patch(
            f"{PREFIX}/kb/{kb_id}",
            json={"retrieval_top_k": 10, "enable_rerank": True},
            headers=auth_headers,
        )
        assert update_resp.status_code == 200
        data = update_resp.json()["data"]
        assert data["retrieval_top_k"] == 10
        assert data["enable_rerank"] is True

    def test_update_other_user_kb_returns_404(self, client: TestClient, kb_payload: dict):
        from tests.conftest import register_and_login
        token_owner = register_and_login(client, "owner_up", "Pass@1234")
        token_other = register_and_login(client, "visitor_up", "Pass@1234")

        headers_owner = {"Authorization": f"Bearer {token_owner}"}
        headers_other = {"Authorization": f"Bearer {token_other}"}

        create_resp = client.post(f"{PREFIX}/kb", json=kb_payload, headers=headers_owner)
        kb_id = create_resp.json()["data"]["id"]

        resp = client.patch(f"{PREFIX}/kb/{kb_id}", json={"retrieval_top_k": 20}, headers=headers_other)
        assert resp.json()["code"] == 404


class TestKBDelete:
    def test_delete_success(self, client: TestClient, auth_headers: dict, kb_payload: dict):
        create_resp = client.post(f"{PREFIX}/kb", json=kb_payload, headers=auth_headers)
        kb_id = create_resp.json()["data"]["id"]

        del_resp = client.delete(f"{PREFIX}/kb/{kb_id}", headers=auth_headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["code"] == 200

        list_resp = client.get(f"{PREFIX}/kb", headers=auth_headers)
        assert list_resp.json()["data"] == []

    def test_delete_nonexistent(self, client: TestClient, auth_headers: dict):
        resp = client.delete(f"{PREFIX}/kb/99999", headers=auth_headers)
        assert resp.json()["code"] == 404
