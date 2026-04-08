from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_session.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retrieved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    citations_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 三链路扩展字段 ────────────────────────────────────────────
    # intent: casual_chat / data_query / doc_search
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="意图类型")
    # 对于 data_query: 存储生成的 SQL
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Text2SQL 生成的 SQL")
    # 对于 data_query: 存储 SQL 执行结果 (JSON)
    sql_result_json: Mapped[str | None] = mapped_column(Text, nullable=True, comment="SQL 查询结果")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
