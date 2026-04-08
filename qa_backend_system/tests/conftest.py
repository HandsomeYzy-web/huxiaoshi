"""
测试配置与共享 Fixtures。

使用 SQLite 内存库替代 MySQL，用 unittest.mock 隔离 Milvus / MinIO / Redis。
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import settings
from core.database import get_db
from main import app
from models.entities.base import Base

# ─────────────────────────────────────────────
# SQLite 内存数据库（每个测试模块独立）
# ─────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Session 级别：建表一次，测试结束后销毁。"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def reset_tables():
    """每个测试前清空所有表，保持隔离。"""
    yield
    for table in reversed(Base.metadata.sorted_tables):
        TestingSessionLocal().execute(table.delete())
        TestingSessionLocal().commit()


@pytest.fixture(scope="session")
def client():
    """共享 TestClient，Session 级别。"""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────
# Mock 外部服务
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_external_services():
    """隔离所有外部服务（Milvus / MinIO / Redis / Celery）。"""
    with (
        patch("repositories.milvus_repo.milvus_repo.ensure_collection"),
        patch("repositories.milvus_repo.milvus_repo.insert_chunks"),
        patch("repositories.milvus_repo.milvus_repo.search_chunks", return_value=[]),
        patch("repositories.milvus_repo.milvus_repo.search_chunks_across_kbs", return_value=[]),
        patch("repositories.milvus_repo.milvus_repo.delete_chunks_by_file_id"),
        patch("repositories.milvus_repo.milvus_repo.delete_chunks_by_kb_id"),
        patch("repositories.minio_repo.minio_repo.upload_file_bytes"),
        patch("repositories.minio_repo.minio_repo.delete_file"),
        patch("repositories.minio_repo.minio_repo.delete_files_with_prefix"),
        patch("tasks.document_tasks.process_document_task.delay"),
        patch("repositories.redis_repo.redis_repo.ping", return_value=True),
    ):
        yield


# ─────────────────────────────────────────────
# 身份认证 Helpers
# ─────────────────────────────────────────────

def register_and_login(client: TestClient, username: str = "testuser", password: str = "Test@1234") -> str:
    """注册并登录，返回 Bearer token。"""
    client.post(f"{settings.API_V1_STR}/auth/register", json={
        "username": username,
        "email": f"{username}@test.com",
        "password": password,
    })
    resp = client.post(f"{settings.API_V1_STR}/auth/login", json={
        "username": username,
        "password": password,
    })
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


@pytest.fixture
def auth_headers(client: TestClient) -> dict:
    """提供已认证的 Authorization 请求头。"""
    token = register_and_login(client)
    return {"Authorization": f"Bearer {token}"}
