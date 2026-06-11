"""Text2SQL SQL 执行服务。

在「目标业务库」上执行最终 SQL 并把结果转成前端可消费的结构。执行前会强制补 LIMIT，
并按配置开启只读事务、设置最大执行时间，避免误写数据或慢查询拖垮业务库；
同时把 Decimal/日期/bytes 等类型归一化为 JSON 友好的值。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from core.config import settings
from services.text2sql.sql_dialect import (
    DB_TYPE_MYSQL,
    normalize_db_type,
    transpile_for_execution,
)

class Text2SQLExecutorService:
    """执行 SQL 并把结果转换成前端可消费的数据结构。"""
    def __init__(
        self,
        engine_provider: Callable[[Session], Engine],
        ensure_limit: Callable[[str], str],
        db_type_provider: Callable[[Session], str] | None = None,
    ):
        """注入数据库引擎提供器、SQL 限流器，以及（可选）当前连接库类型提供器。

        db_type_provider 缺省（None）时按 MySQL 处理，兼容仅注入前两者的旧调用/测试桩。
        """
        self._engine_provider = engine_provider
        self._ensure_limit = ensure_limit
        self._db_type_provider = db_type_provider

    def _resolve_db_type(self, db: Session) -> str:
        """解析当前连接的库类型；无提供器或解析失败时回退 MySQL。"""
        if self._db_type_provider is None:
            return DB_TYPE_MYSQL
        try:
            return normalize_db_type(self._db_type_provider(db))
        except Exception:  # noqa: BLE001
            return DB_TYPE_MYSQL

    def _apply_session_guards(self, conn, db_type: str) -> None:
        """按库类型设置会话级保护：只读事务 + 语句超时。

        - MySQL：SET SESSION TRANSACTION READ ONLY（强制成功，失败即报错）+ MAX_EXECUTION_TIME。
        - SQL Server：无等价的会话级只读语句，写操作由校验器（禁写关键字 + 仅允许单条 SELECT）拦截，
          建议业务库再配一个仅有 SELECT 权限的只读账号做纵深防御。
        """
        if db_type != DB_TYPE_MYSQL:
            return
        try:
            transaction_mode = "READ ONLY" if settings.TEXT2SQL_READONLY else "READ WRITE"
            conn.execute(text(f"SET SESSION TRANSACTION {transaction_mode}"))
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("无法设置会话事务模式，请检查数据库事务配置") from exc

        # 设置语句最大执行时间，防止生成的慢查询长时间占用业务库连接（设置失败不致命）。
        timeout_ms = settings.TEXT2SQL_EXEC_TIMEOUT_SECONDS * 1000
        try:
            conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME={timeout_ms}"))
        except Exception:  # noqa: BLE001
            pass

    def execute_sql(self, db: Session, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
        """执行 SQL 并返回列名与行数据。

        SQL 在流水线内部为 MySQL 方言，执行前先补 LIMIT，再按目标库类型转写到对应方言
        （如 SQL Server 的 LIMIT→TOP、反引号→[方括号]）。
        """
        engine = self._engine_provider(db)
        db_type = self._resolve_db_type(db)
        sql = self._ensure_limit(sql)
        sql = transpile_for_execution(sql, db_type)
        with engine.connect() as conn:
            self._apply_session_guards(conn, db_type)

            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows: list[dict[str, Any]] = []

            # 逐行转 dict，并把数据库特有类型归一化为 JSON 可序列化的值。
            for row in result.fetchall():
                row_dict: dict[str, Any] = {}
                for index, column in enumerate(columns):
                    value = row[index]

                    if isinstance(value, Decimal):
                        value = float(value)
                    elif hasattr(value, "isoformat"):
                        value = value.isoformat()
                    elif isinstance(value, bytes):
                        value = value.decode("utf-8", errors="replace")

                    row_dict[column] = value
                rows.append(row_dict)

            return columns, rows

