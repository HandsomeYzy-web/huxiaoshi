import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, computed_field

class Settings(BaseSettings):
    # 基础配置
    PROJECT_NAME: str = "QA Backend System"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # MySQL 配置
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_HOST: str
    MYSQL_PORT: str
    MYSQL_DB: str

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """动态拼装 MySQL 连接字符串"""
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"

    # Redis 配置
    REDIS_HOST: str
    REDIS_PORT: str
    REDIS_PASSWORD: str
    REDIS_DB: int = 0

    @computed_field
    @property
    def REDIS_URI(self) -> str:
        """动态拼装 Redis 连接字符串"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # MinIO 配置
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_SECURE: bool = False
    MINIO_BUCKET_NAME: str = "qa-knowledge-files"

    # Milvus 配置
    MILVUS_HOST: str
    MILVUS_PORT: str

    # AI 大模型配置
    DASHSCOPE_API_KEY: str = ""

    # 指定从 .env 文件读取环境变量
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore" # 忽略 .env 中未在类中定义的额外变量
    )

# 实例化单例，整个项目只需导入这个 settings 即可
# 用法: from core.config import settings
settings = Settings()