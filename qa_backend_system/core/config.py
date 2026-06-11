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

    # ── Elasticsearch ─────────────────────────────────────────────
    ES_HOST: str
    ES_PORT: str
    ES_SCHEME: str = "http"
    ES_VECTOR_DIM: int = 1024
    # 可选认证（本地开发默认无认证，留空即可）
    ES_USERNAME: str = ""
    ES_PASSWORD: str = ""
    ES_API_KEY: str = ""

    @computed_field
    @property
    def ES_URL(self) -> str:
        """根据 Elasticsearch 连接参数动态拼接访问 URL。"""
        return f"{self.ES_SCHEME}://{self.ES_HOST}:{self.ES_PORT}"

    # ── 当前用户（接入统一认证平台）────────────────────────────────
    # 应用自身不做鉴权；当前用户身份由上游统一认证网关通过请求头注入。
    # 本地开发无该请求头时，回退到 DEFAULT_USER_ID。聊天记录据此按用户区分。
    CURRENT_USER_HEADER: str = "X-User-Id"
    DEFAULT_USER_ID: int = 1

    # ── 加密（Text2SQL 连接密码等）────────────────────────────────
    APP_SECRET_KEY: str = ""
    FERNET_KEY: str = ""

    # ── File Upload ───────────────────────────────────────────────
    # 仅支持核心文档格式：源文件存 MinIO，向量+分段存 Elasticsearch，分段元数据存 MySQL
    # 不支持图片、音视频、epub、json、xml 等非文本格式
    MAX_UPLOAD_FILE_SIZE_MB: int = 200
    ALLOWED_FILE_TYPES: List[str] = [
        "pdf", "docx",
        "xlsx", "csv",
        "pptx",
        "txt", "md",
    ]

    # ── Text2SQL (业务数据库，非模型配置) ────────────────────────
    TEXT2SQL_ENABLED: bool = True
    TEXT2SQL_MAX_ROWS: int = 50
    TEXT2SQL_READONLY: bool = True
    TEXT2SQL_EXEC_TIMEOUT_SECONDS: int = 20
    TEXT2SQL_AUTO_REPAIR_ROUNDS: int = 2
    # Self-consistency：生成多个候选 SQL 并按执行结果投票，多数结果胜出；N=1 表示关闭该功能。
    TEXT2SQL_SELF_CONSISTENCY_N: int = 1
    TEXT2SQL_SELF_CONSISTENCY_TEMPERATURE: float = 0.4
    TEXT2SQL_MULTI_TABLE_ENABLED: bool = True
    TEXT2SQL_MAX_JOIN_TABLES: int = 5
    TEXT2SQL_QUERY_LOG_ENABLED: bool = True

    # Enhanced features are disabled by default.
    TEXT2SQL_ENUM_HINT_ENABLED: bool = False
    TEXT2SQL_FEW_SHOT_ENABLED: bool = False
    # 仅当用户评分 >= 该阈值（1-5 星）时，对应查询才会被纳入 few-shot 示例池（默认 5=仅“非常满意”）。
    TEXT2SQL_FEWSHOT_MIN_SCORE: int = 5

    # Schema 剪枝：宽表只保留与问题最相关的前 N 列进提示词，降噪 + 省 token（默认关闭）。
    TEXT2SQL_SCHEMA_PRUNE_ENABLED: bool = False
    TEXT2SQL_SCHEMA_MAX_COLS_PER_TABLE: int = 40
    TEXT2SQL_SCHEMA_PRUNE_KEEP_COLS: int = 25

    TEXT2SQL_ENUM_HINT_SAMPLE_ROWS: int = 100
    TEXT2SQL_ENUM_HINT_TOP_VALUES: int = 5
    TEXT2SQL_ENUM_HINT_MAX_COLUMNS_PER_TABLE: int = 6
    TEXT2SQL_ENUM_HINT_MAX_WORKERS: int = 4
    TEXT2SQL_ENUM_HINT_PROBE_TIMEOUT_MS: int = 300
    TEXT2SQL_ENUM_HINT_MAX_PROMPT_CHARS: int = 2400
    TEXT2SQL_ENUM_HINT_MAX_TABLES: int = 3

    TABLE_ROUTE_KB_ID: int = 0
    TEXT2SQL_FEWSHOT_KB_ID: int = 0
    # ── 知识库隔离（text2SQL 专用保留库）──────────────────────────
    # 表路由仅检索「table_desc」库、few-shot 仅检索「few-shot」库，
    # 文档问答自动排除这两个保留库。ID 配置（上方）优先，名称匹配兜底；
    # 名称比较忽略大小写并把 - 与 _ 视为等价。置空名称即关闭按名称解析。
    TEXT2SQL_TABLE_DESC_KB_NAME: str = "table_desc"
    TEXT2SQL_FEWSHOT_KB_NAME: str = "few-shot"
    TABLE_ROUTE_KB_SEARCH_TOP_K: int = 120
    TABLE_ROUTE_KB_RECALL_CANDIDATES: int = 60
    TABLE_ROUTE_MAX_CANDIDATES: int = 10
    TABLE_ROUTE_SEMANTIC_SCORE_WEIGHT: float = 10.0
    TABLE_ROUTE_KEYWORD_SCORE_WEIGHT: float = 1.0
    TABLE_ROUTE_PROFILE_SCORE_WEIGHT: float = 2.0
    TABLE_ROUTE_NAME_EXACT_MATCH_SCORE: float = 2.0
    TABLE_ROUTE_NAME_TOKEN_MATCH_SCORE: float = 0.85
    TABLE_ROUTE_PROFILE_TOKEN_MATCH_SCORE: float = 0.18
    TABLE_ROUTE_PROFILE_SCORE_CAP: float = 3.0

    # ── 聊天表格上传分析（短期存储，分析成功后即删，TTL 兜底清理）──
    CHAT_UPLOAD_MAX_SIZE_MB: int = 10
    CHAT_UPLOAD_MAX_ROWS: int = 50000
    CHAT_UPLOAD_TTL_MINUTES: int = 30
    CHAT_UPLOAD_RESULT_MAX_ROWS: int = 200

    # ── General ───────────────────────────────────────────────────
    DEFAULT_RETRIEVAL_TOP_K: int = 5
    LLM_TIMEOUT: int = 120

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
