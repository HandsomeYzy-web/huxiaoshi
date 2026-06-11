"""Text2SQL 查询日志服务。

记录每次查询的成功/失败、生成与最终 SQL、命中表、行数、耗时、是否修复等审计信息，
并支持用户对结果打满意度评分（高分查询可回流为 few-shot 样例）。是审计与质量回流的入口。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from repositories.text2sql_query_log_repo import Text2SQLQueryLogRepository
from models.schemas.text2sql_schema import Text2SQLQueryLogItem

class Text2SQLLogService:
    """封装查询日志写入与读取。"""
    def _serialize_selected_tables(self, runtime_config: dict[str, Any]) -> str:
        """把运行时表范围序列化为 JSON 字符串。"""
        return json.dumps(runtime_config.get("selected_tables", []), ensure_ascii=False)

    @staticmethod
    def _extract_relation_guard_used(runtime_config: dict[str, Any]) -> bool:
        """从运行时配置中读取「本次是否进入带关系约束的多表模式」标记。"""
        return bool(runtime_config.get("relation_guard_used", False))

    def create_success_log(
        self,
        *,
        db: Session,
        user_id: int,
        question: str,
        generated_sql: str | None,
        final_sql: str | None,
        runtime_config: dict[str, Any],
        row_count: int,
        duration_ms: int,
        repaired: bool,
    ) -> int | None:
        """写入一次成功查询的日志，返回新日志的 id（旧库结构无法回填时返回 None）。"""
        log = Text2SQLQueryLogRepository(db).create(
            user_id=user_id,
            question=question,
            generated_sql=generated_sql,
            final_sql=final_sql,
            status="success",
            error_message=None,
            selected_tables=self._serialize_selected_tables(runtime_config),
            relation_guard_used=self._extract_relation_guard_used(runtime_config),
            row_count=row_count,
            duration_ms=duration_ms,
            repaired=repaired,
        )
        log_id = getattr(log, "id", None)
        return int(log_id) if log_id else None

    def update_feedback(self, db: Session, *, log_id: int, user_id: int, score: int) -> bool:
        """记录用户对某条查询结果的满意度评分（1-5 星），仅日志所属用户可修改。"""
        return Text2SQLQueryLogRepository(db).update_feedback(
            log_id=log_id,
            user_id=user_id,
            score=score,
        )

    def create_failed_log(
        self,
        *,
        db: Session,
        user_id: int,
        question: str,
        generated_sql: str | None,
        final_sql: str | None,
        runtime_config: dict[str, Any],
        error_message: str,
        duration_ms: int,
        repaired: bool,
    ) -> None:
        """写入一次失败查询的日志。"""
        Text2SQLQueryLogRepository(db).create(
            user_id=user_id,
            question=question,
            generated_sql=generated_sql,
            final_sql=final_sql,
            status="failed",
            error_message=error_message,
            selected_tables=self._serialize_selected_tables(runtime_config),
            relation_guard_used=self._extract_relation_guard_used(runtime_config),
            row_count=None,
            duration_ms=duration_ms,
            repaired=repaired,
        )

    def list_logs(self, db: Session, user_id: int, limit: int = 20) -> list[Text2SQLQueryLogItem]:
        """读取最近的查询日志列表。"""
        logs = Text2SQLQueryLogRepository(db).list_latest(user_id=user_id, limit=limit)
        return [Text2SQLQueryLogItem.model_validate(item) for item in logs]

