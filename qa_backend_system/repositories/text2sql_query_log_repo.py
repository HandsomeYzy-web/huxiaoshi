"""text2sql_query_log 表的数据访问层（查询日志的持久化与读取）。

除常规读写外，本仓储内置「尽力而为」的 schema 兼容机制：feedback_score、relation_guard_used
这两列是后续版本新增的，运行时若发现旧库缺列会尝试自动 ALTER 补上；补列失败或执行报「未知列」
时，自动退回到「不含新列」的兼容写/读路径，保证老库也能正常记录与读取日志。
检查结果用类级标志缓存，避免每次请求都探测表结构。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from models.entities.text2sql_query_log import Text2SQLQueryLog


class Text2SQLQueryLogRepository:
    """Text2SQL 查询日志的持久化与查询辅助。"""

    # 类级缓存：新增列是否已探测过、当前库是否可用，避免重复 ALTER/探测。
    _relation_guard_column_checked: bool = False
    _relation_guard_column_available: bool = True
    _feedback_score_column_checked: bool = False
    _feedback_score_column_available: bool = True

    def __init__(self, db: Session):
        """注入数据库会话。"""
        self.db = db

    def ensure_feedback_score_column(self) -> bool:
        """尽力而为的兼容：若 feedback_score 列缺失则自动补建；结果按方言适配并缓存。"""
        cls = self.__class__
        if cls._feedback_score_column_checked:
            return cls._feedback_score_column_available

        cls._feedback_score_column_checked = True
        cls._feedback_score_column_available = True
        try:
            bind = self.db.get_bind()
            inspector = inspect(bind)
            columns = {
                str(col.get("name") or "").lower()
                for col in inspector.get_columns(Text2SQLQueryLog.__tablename__)
            }
            if "feedback_score" in columns:
                return True

            dialect_name = str(getattr(bind.dialect, "name", "") or "").lower()
            if dialect_name == "mysql":
                ddl = "ALTER TABLE text2sql_query_log ADD COLUMN feedback_score INT NULL"
            else:
                ddl = "ALTER TABLE text2sql_query_log ADD COLUMN feedback_score INTEGER"
            self.db.execute(text(ddl))
            self.db.commit()
            return True
        except Exception:  # noqa: BLE001
            self.db.rollback()
            cls._feedback_score_column_available = False
            return False

    def update_feedback(self, *, log_id: int, user_id: int, score: int) -> bool:
        """更新某条查询日志的用户评分，仅允许日志所属用户修改。返回是否命中记录。

        先按 (id, user_id) 校验归属再更新——避免依赖 UPDATE 的 rowcount
        （MySQL 默认只统计“值发生变化”的行，重复提交同一分数会误判为失败）。
        """
        self.ensure_feedback_score_column()
        owner = self.db.execute(
            text("SELECT id FROM text2sql_query_log WHERE id = :log_id AND user_id = :user_id"),
            {"log_id": int(log_id), "user_id": int(user_id)},
        ).first()
        if owner is None:
            return False
        self.db.execute(
            text(
                "UPDATE text2sql_query_log SET feedback_score = :score "
                "WHERE id = :log_id AND user_id = :user_id"
            ),
            {"score": int(score), "log_id": int(log_id), "user_id": int(user_id)},
        )
        self.db.commit()
        return True

    @staticmethod
    def _is_unknown_relation_guard_column_error(exc: Exception) -> bool:
        """判断异常是否为「relation_guard_used 列不存在」——据此触发降级到兼容路径。"""
        message = str(exc).lower()
        return "unknown column" in message and "relation_guard_used" in message

    @staticmethod
    def _as_datetime(value: object) -> datetime:
        """把原始值安全转为 datetime（非 datetime 时回退为当前时间）。"""
        if isinstance(value, datetime):
            return value
        return datetime.now()

    def _ensure_relation_guard_column(self) -> bool:
        """尽力而为的兼容：若 relation_guard_used 列缺失则自动补建；结果按方言适配并缓存。"""
        cls = self.__class__
        if cls._relation_guard_column_checked:
            return cls._relation_guard_column_available

        cls._relation_guard_column_checked = True
        cls._relation_guard_column_available = True
        try:
            bind = self.db.get_bind()
            inspector = inspect(bind)
            columns = {
                str(col.get("name") or "").lower()
                for col in inspector.get_columns(Text2SQLQueryLog.__tablename__)
            }
            if "relation_guard_used" in columns:
                return True

            dialect_name = str(getattr(bind.dialect, "name", "") or "").lower()
            if dialect_name == "mysql":
                ddl = (
                    "ALTER TABLE text2sql_query_log "
                    "ADD COLUMN relation_guard_used TINYINT(1) NOT NULL DEFAULT 0"
                )
            else:
                ddl = (
                    "ALTER TABLE text2sql_query_log "
                    "ADD COLUMN relation_guard_used BOOLEAN NOT NULL DEFAULT 0"
                )
            self.db.execute(text(ddl))
            self.db.commit()
            return True
        except Exception:  # noqa: BLE001
            self.db.rollback()
            cls._relation_guard_column_available = False
            return False

    def _create_without_relation_guard(
        self,
        *,
        user_id: int,
        question: str,
        generated_sql: str | None,
        final_sql: str | None,
        status: str,
        error_message: str | None,
        selected_tables: str | None,
        row_count: int | None,
        duration_ms: int | None,
        repaired: bool,
    ) -> Text2SQLQueryLog:
        """兼容写入：面向缺少 relation_guard_used 列的旧库，用显式列清单 INSERT。"""
        sql = text(
            """
            INSERT INTO text2sql_query_log
            (user_id, question, generated_sql, final_sql, status, error_message, selected_tables, row_count, duration_ms, repaired)
            VALUES
            (:user_id, :question, :generated_sql, :final_sql, :status, :error_message, :selected_tables, :row_count, :duration_ms, :repaired)
            """
        )
        self.db.execute(
            sql,
            {
                "user_id": int(user_id),
                "question": question,
                "generated_sql": generated_sql,
                "final_sql": final_sql,
                "status": status,
                "error_message": error_message,
                "selected_tables": selected_tables,
                "row_count": row_count,
                "duration_ms": duration_ms,
                "repaired": bool(repaired),
            },
        )
        self.db.commit()
        return Text2SQLQueryLog(
            user_id=int(user_id),
            question=question,
            generated_sql=generated_sql,
            final_sql=final_sql,
            status=status,
            error_message=error_message,
            selected_tables=selected_tables,
            relation_guard_used=False,
            row_count=row_count,
            duration_ms=duration_ms,
            repaired=bool(repaired),
            created_at=datetime.now(),
        )

    def create(
        self,
        *,
        user_id: int,
        question: str,
        generated_sql: str | None,
        final_sql: str | None,
        status: str,
        error_message: str | None,
        selected_tables: str | None,
        relation_guard_used: bool,
        row_count: int | None,
        duration_ms: int | None,
        repaired: bool,
    ) -> Text2SQLQueryLog:
        """写入一条查询日志。新列不可用时走兼容写入；提交时若报「未知列」也会降级重试。"""
        feedback_column_ok = self.ensure_feedback_score_column()
        if not self._ensure_relation_guard_column() or not feedback_column_ok:
            return self._create_without_relation_guard(
                user_id=user_id,
                question=question,
                generated_sql=generated_sql,
                final_sql=final_sql,
                status=status,
                error_message=error_message,
                selected_tables=selected_tables,
                row_count=row_count,
                duration_ms=duration_ms,
                repaired=repaired,
            )

        log = Text2SQLQueryLog(
            user_id=user_id,
            question=question,
            generated_sql=generated_sql,
            final_sql=final_sql,
            status=status,
            error_message=error_message,
            selected_tables=selected_tables,
            relation_guard_used=bool(relation_guard_used),
            row_count=row_count,
            duration_ms=duration_ms,
            repaired=repaired,
        )
        self.db.add(log)
        try:
            self.db.commit()
            self.db.refresh(log)
            return log
        except OperationalError as exc:
            if not self._is_unknown_relation_guard_column_error(exc):
                raise
            self.db.rollback()
            self.__class__._relation_guard_column_available = False
            return self._create_without_relation_guard(
                user_id=user_id,
                question=question,
                generated_sql=generated_sql,
                final_sql=final_sql,
                status=status,
                error_message=error_message,
                selected_tables=selected_tables,
                row_count=row_count,
                duration_ms=duration_ms,
                repaired=repaired,
            )

    def _list_latest_without_relation_guard(self, user_id: int, limit: int) -> list[Text2SQLQueryLog]:
        """兼容读取：面向缺少新列的旧库，用显式列清单查询并手工组装实体（新列填默认值）。"""
        safe_limit = max(1, int(limit))
        rows = self.db.execute(
            text(
                f"""
                SELECT
                    id,
                    user_id,
                    question,
                    generated_sql,
                    final_sql,
                    status,
                    error_message,
                    selected_tables,
                    row_count,
                    duration_ms,
                    repaired,
                    created_at
                FROM text2sql_query_log
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT {safe_limit}
                """
            ),
            {"user_id": int(user_id)},
        ).mappings().all()
        result: list[Text2SQLQueryLog] = []
        for item in rows:
            result.append(
                Text2SQLQueryLog(
                    id=int(item.get("id") or 0),
                    user_id=int(item.get("user_id") or 0),
                    question=str(item.get("question") or ""),
                    generated_sql=item.get("generated_sql"),
                    final_sql=item.get("final_sql"),
                    status=str(item.get("status") or ""),
                    error_message=item.get("error_message"),
                    selected_tables=item.get("selected_tables"),
                    relation_guard_used=False,
                    row_count=item.get("row_count"),
                    duration_ms=item.get("duration_ms"),
                    repaired=bool(item.get("repaired")),
                    created_at=self._as_datetime(item.get("created_at")),
                )
            )
        return result

    def list_latest(self, user_id: int, limit: int = 20) -> list[Text2SQLQueryLog]:
        """按创建时间倒序读取某用户最近的日志；新列不可用或报「未知列」时降级到兼容读取。"""
        feedback_column_ok = self.ensure_feedback_score_column()
        if not self._ensure_relation_guard_column() or not feedback_column_ok:
            return self._list_latest_without_relation_guard(user_id=user_id, limit=limit)
        try:
            return (
                self.db.query(Text2SQLQueryLog)
                .filter(Text2SQLQueryLog.user_id == user_id)
                .order_by(desc(Text2SQLQueryLog.created_at))
                .limit(limit)
                .all()
            )
        except OperationalError as exc:
            if not self._is_unknown_relation_guard_column_error(exc):
                raise
            self.db.rollback()
            self.__class__._relation_guard_column_available = False
            return self._list_latest_without_relation_guard(user_id=user_id, limit=limit)