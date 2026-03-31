"""
认证接口测试：注册、登录、获取当前用户信息、无效 Token 访问。
"""
import pytest
from fastapi.testclient import TestClient

from core.config import settings


PREFIX = settings.API_V1_STR


class TestAuthRegister:
    def test_register_success(self, client: TestClient):
        resp = client.post(f"{PREFIX}/auth/register", json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "Alice@1234",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["username"] == "alice"

    def test_register_duplicate_username(self, client: TestClient):
        payload = {"username": "bob", "email": "bob@example.com", "password": "Bob@1234"}
        client.post(f"{PREFIX}/auth/register", json=payload)
        resp = client.post(f"{PREFIX}/auth/register", json=payload)
        assert resp.status_code == 200
        assert resp.json()["code"] == 400

    def test_register_invalid_email(self, client: TestClient):
        resp = client.post(f"{PREFIX}/auth/register", json={
            "username": "charlie",
            "email": "not-an-email",
            "password": "Charlie@1234",
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 422


class TestAuthLogin:
    def test_login_success(self, client: TestClient):
        client.post(f"{PREFIX}/auth/register", json={
            "username": "dave",
            "email": "dave@example.com",
            "password": "Dave@1234",
        })
        resp = client.post(f"{PREFIX}/auth/login", json={
            "username": "dave",
            "password": "Dave@1234",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client: TestClient):
        client.post(f"{PREFIX}/auth/register", json={
            "username": "eve",
            "email": "eve@example.com",
            "password": "Eve@1234",
        })
        resp = client.post(f"{PREFIX}/auth/login", json={
            "username": "eve",
            "password": "wrong",
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 401

    def test_login_nonexistent_user(self, client: TestClient):
        resp = client.post(f"{PREFIX}/auth/login", json={
            "username": "ghost",
            "password": "anything",
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 401


class TestAuthMe:
    def test_get_me_success(self, client: TestClient, auth_headers: dict):
        resp = client.get(f"{PREFIX}/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "testuser"

    def test_get_me_no_token(self, client: TestClient):
        resp = client.get(f"{PREFIX}/auth/me")
        assert resp.status_code == 200
        assert resp.json()["code"] == 401

    def test_get_me_invalid_token(self, client: TestClient):
        resp = client.get(f"{PREFIX}/auth/me", headers={"Authorization": "Bearer invalid.token"})
        assert resp.status_code == 200
        assert resp.json()["code"] == 401
