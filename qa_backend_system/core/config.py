
from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "QA Backend System"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # ── CORS ──────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["*"]

    # ── MySQL ─────────────────────────────────────────────────────
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_HOST: str
    MYSQL_PORT: str
    MYSQL_DB: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"
        )

    # ── Redis ─────────────────────────────────────────────────────
    REDIS_HOST: str
    REDIS_PORT: str
    REDIS_PASSWORD: str
    REDIS_DB: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_URI(self) -> str:
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
    MILVUS_VECTOR_DIM: int = 4096

    # ── Embedding ─────────────────────────────────────────────────
    EMBEDDING_BASE_URL: str
    EMBEDDING_API_KEY: str
    EMBEDDING_MODEL: str

    # ── LLM ───────────────────────────────────────────────────────
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_TIMEOUT: int = 120

    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_MODEL_NAME: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_RETRIEVAL_TOP_K: int = 5

    # ── Reranker ──────────────────────────────────────────────────
    RERANKER_ENABLED: bool = False
    RERANKER_BASE_URL: str = ""
    RERANKER_API_KEY: str = ""
    RERANKER_MODEL: str = ""

    # ── Text2SQL ──────────────────────────────────────────────────
    TEXT2SQL_ENABLED: bool = False
    TEXT2SQL_DB_URI: str = ""  # 业务数据库连接串
    TEXT2SQL_MAX_ROWS: int = 50  # 查询结果最大返回行数
    TEXT2SQL_READONLY: bool = True  # 只允许 SELECT

    # ── JWT ────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天

    # ── File Upload ───────────────────────────────────────────────
    MAX_UPLOAD_FILE_SIZE_MB: int = 200
    ALLOWED_FILE_TYPES: list[str] = [
        "pdf", "docx", "doc", "xlsx", "xls", "csv",
        "pptx", "ppt", "txt", "md", "html", "htm",
        "png", "jpg", "jpeg", "bmp", "tiff", "webp",
        "json", "xml", "rst", "rtf", "epub",
    ]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def MAX_UPLOAD_FILE_SIZE_BYTES(self) -> int:
        return self.MAX_UPLOAD_FILE_SIZE_MB * 1024 * 1024

    @computed_field  # type: ignore[prop-decorator]
    @property
    def EFFECTIVE_LLM_BASE_URL(self) -> str:
        return self.LLM_BASE_URL or self.DASHSCOPE_BASE_URL

    @computed_field  # type: ignore[prop-decorator]
    @property
    def EFFECTIVE_LLM_API_KEY(self) -> str:
        return self.LLM_API_KEY or self.DASHSCOPE_API_KEY

    @computed_field  # type: ignore[prop-decorator]
    @property
    def EFFECTIVE_LLM_MODEL(self) -> str:
        return self.LLM_MODEL or self.DASHSCOPE_MODEL_NAME

    @model_validator(mode="after")
    def _validate_security(self):
        if self.JWT_SECRET_KEY == "change-me-in-production-use-a-long-random-string":
            import warnings
            warnings.warn(
                "JWT_SECRET_KEY is using the insecure default value! "
                "Set a strong secret in your .env file for production.",
                stacklevel=2,
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
