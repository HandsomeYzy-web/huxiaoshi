from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Text2SQLQueryLog(Base):
    """Text2SQL 查询日志：记录每次问答的请求与执行结果，用于审计与质量回流。

    status 为 success/failed；generated_sql 为模型原始 SQL、final_sql 为后处理/修复后的最终 SQL；
    feedback_score 为用户满意度（高分记录会被 few-shot 服务回流为示范样例）。
    """

    __tablename__ = "text2sql_query_log"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_sql: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_tables: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    relation_guard_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    repaired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 用户满意度评分（1-5 星）；NULL 表示未评分。>= TEXT2SQL_FEWSHOT_MIN_SCORE 时纳入 few-shot 示例池。
    feedback_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

