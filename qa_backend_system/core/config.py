"""配置文件：集中管理所有系统配置项，通过 .env 文件或环境变量注入。"""

from typing import List

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """系统全局配置类，基于 pydantic-settings 自动从环境变量/.env 文件读取配置。"""
    PROJECT_NAME: str = "QA Backend System"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # ── CORS ──────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["http://localhost:5173"]

    # ── MySQL ─────────────────────────────────────────────────────
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_HOST: str
    MYSQL_PORT: str
    MYSQL_DB: str

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """根据 MySQL 连接参数动态拼接 SQLAlchemy 数据库连接 URI。"""
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"
        )

    # ── Redis ─────────────────────────────────────────────────────
    REDIS_HOST: str
    REDIS_PORT: str
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    @computed_field
    @property
    def REDIS_URI(self) -> str:
        """根据 Redis 连接参数动态拼接 Redis 连接 URI。"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ── MinIO ─────────────────────────────────────────────────────
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_SECURE: bool = False
    MINIO_BUCKET_NAME: str = "qa-knowledge-files"

    # ── Milvus ────────────────────────────────────────────────────
    MILVUS_HOST: str
    MILVUS_PORT: str

    # ── JWT ────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天

    # ── File Upload ───────────────────────────────────────────────
    # 仅支持核心文档格式：源文件存 MinIO，向量+分段存 Milvus，分段元数据存 MySQL
    # 不支持图片、音视频、epub、json、xml 等非文本格式
    MAX_UPLOAD_FILE_SIZE_MB: int = 200
    ALLOWED_FILE_TYPES: List[str] = [
        "pdf", "docx",
        "xlsx", "csv",
        "pptx",
        "txt", "md",
    ]

    # ── Text2SQL (业务数据库，非模型配置) ────────────────────────
    TEXT2SQL_ENABLED: bool = False
    TEXT2SQL_DB_URI: str = ""
    TEXT2SQL_MAX_ROWS: int = 50
    TEXT2SQL_READONLY: bool = True

    # ── General ───────────────────────────────────────────────────
    DEFAULT_RETRIEVAL_TOP_K: int = 5
    LLM_TIMEOUT: int = 120
    INTENT_ENHANCED_ROUTING_ENABLED: bool = True
    INTENT_CONFIDENCE_THRESHOLD: float = 0.85
    INTENT_MAX_HISTORY_MESSAGES: int = 6

    @computed_field
    @property
    def MAX_UPLOAD_FILE_SIZE_BYTES(self) -> int:
        """将文件上传大小限制从 MB 转换为字节。"""
        return self.MAX_UPLOAD_FILE_SIZE_MB * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# 全局配置单例，供项目各模块引用
settings = Settings()
