from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings
from models.entities import Base

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _patch_legacy_knowledge_base_columns() -> None:
    """
    Ensure old `knowledge_base` tables are compatible with current ORM fields.
    `create_all` will not alter existing tables, so we patch missing columns.
    """
    if engine.dialect.name != "mysql":
        return

    inspector = inspect(engine)
    if "knowledge_base" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("knowledge_base")}
    alter_clauses: list[str] = []

    if "default_separators" not in existing_columns:
        alter_clauses.append(
            "ADD COLUMN default_separators TEXT NULL COMMENT 'Default separators as JSON array'"
        )
    if "retrieval_top_k" not in existing_columns:
        alter_clauses.append(
            "ADD COLUMN retrieval_top_k INT NOT NULL DEFAULT 5 COMMENT 'Retrieval top-k'"
        )
    if "retrieval_score_threshold" not in existing_columns:
        alter_clauses.append(
            "ADD COLUMN retrieval_score_threshold DOUBLE NOT NULL DEFAULT 0 COMMENT 'Retrieval threshold'"
        )
    if "enable_rerank" not in existing_columns:
        alter_clauses.append(
            "ADD COLUMN enable_rerank TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Enable rerank'"
        )
    backfill_purpose = "purpose" not in existing_columns
    if backfill_purpose:
        alter_clauses.append(
            "ADD COLUMN purpose VARCHAR(32) NOT NULL DEFAULT 'document' "
            "COMMENT 'KB purpose: document/table_desc/few_shot'"
        )

    if not alter_clauses:
        return

    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE knowledge_base {', '.join(alter_clauses)}"))
        if backfill_purpose:
            # 老数据按名称约定回填用途（与 kb_scope 的名称兜底规则一致：忽略大小写，- 与 _ 等价）。
            conn.execute(text(
                "UPDATE knowledge_base SET purpose = 'table_desc' "
                "WHERE LOWER(REPLACE(name, '-', '_')) = 'table_desc'"
            ))
            conn.execute(text(
                "UPDATE knowledge_base SET purpose = 'few_shot' "
                "WHERE LOWER(REPLACE(name, '-', '_')) = 'few_shot'"
            ))


def _patch_legacy_knowledge_file_columns() -> None:
    """
    Ensure old `knowledge_file` tables are compatible with current ORM fields.
    """
    if engine.dialect.name != "mysql":
        return

    inspector = inspect(engine)
    if "knowledge_file" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("knowledge_file")}
    alter_clauses: list[str] = []

    if "custom_chunk_size" not in existing_columns:
        alter_clauses.append(
            "ADD COLUMN custom_chunk_size INT NULL COMMENT 'Custom chunk size'"
        )
    if "custom_chunk_overlap" not in existing_columns:
        alter_clauses.append(
            "ADD COLUMN custom_chunk_overlap INT NULL COMMENT 'Custom chunk overlap'"
        )
    if "custom_separators" not in existing_columns:
        alter_clauses.append(
            "ADD COLUMN custom_separators TEXT NULL COMMENT 'Custom separators as JSON array'"
        )

    if not alter_clauses:
        return

    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE knowledge_file {', '.join(alter_clauses)}"))


def _patch_legacy_chat_session_columns() -> None:
    """
    Ensure legacy `chat_session` table is compatible with current runtime behavior.
    Some old schemas contain `is_deleted` without a default value, which breaks insert.
    """
    if engine.dialect.name != "mysql":
        return

    inspector = inspect(engine)
    if "chat_session" not in inspector.get_table_names():
        return

    columns = inspector.get_columns("chat_session")
    existing_columns = {col["name"] for col in columns}
    alter_clauses: list[str] = []

    if "is_deleted" not in existing_columns:
        alter_clauses.append(
            "ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete flag'"
        )
    else:
        is_deleted_column = next((col for col in columns if col.get("name") == "is_deleted"), None)
        if is_deleted_column is not None:
            default_raw = is_deleted_column.get("default")
            default_text = "" if default_raw is None else str(default_raw).strip().strip("'").strip('"').lower()
            nullable = bool(is_deleted_column.get("nullable", True))
            has_default_zero = default_text in {"0", "b'0'", "false"}
            if nullable or not has_default_zero:
                alter_clauses.append(
                    "MODIFY COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete flag'"
                )

    if not alter_clauses:
        return

    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE chat_session {', '.join(alter_clauses)}"))


def init_db() -> None:
    from core.logger import logger

    try:
        Base.metadata.create_all(bind=engine)
        _patch_legacy_knowledge_base_columns()
        _patch_legacy_knowledge_file_columns()
        _patch_legacy_chat_session_columns()
        logger.info("数据库表结构同步成功")
    except Exception as exc:
        logger.error(f"数据库初始化失败: {exc}")
        raise
