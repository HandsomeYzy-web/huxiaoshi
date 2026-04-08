"""One-time migration: add intent/generated_sql/sql_result_json to chat_message."""
from sqlalchemy import create_engine, text

from core.config import settings

engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
with engine.connect() as conn:
    conn.execute(text("ALTER TABLE chat_message ADD COLUMN intent VARCHAR(32) NULL COMMENT '意图类型'"))
    conn.execute(text("ALTER TABLE chat_message ADD COLUMN generated_sql TEXT NULL COMMENT 'Text2SQL生成的SQL'"))
    conn.execute(text("ALTER TABLE chat_message ADD COLUMN sql_result_json TEXT NULL COMMENT 'SQL查询结果JSON'"))
    conn.commit()
    print("OK: 3 columns added to chat_message")
