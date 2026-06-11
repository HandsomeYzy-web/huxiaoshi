"""Text2SQL 枚举值提示服务（增强能力，按 TEXT2SQL_ENUM_HINT_ENABLED 开关启用）。

针对候选表中「像枚举」的字段（varchar/char/tinyint，排除主键与各类 *_id），到业务库抽样
其高频取值，作为 enum_hints_json 追加进生成提示词。这样模型写过滤条件时能用真实取值
（如 status='已完成' 而非臆造的 '完成'），显著降低「SQL 合法但查不到数据」的情况。

工程上做了多重保护：多列并发探测、单列设置最大执行时间、按提示词字符上限自动裁剪，
任何异常或超时都安全退回原始提示词（degraded），并打点记录探测/命中/超时情况。
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from core.config import settings
from services.text2sql.schema_service import Text2SQLSchemaService
from services.text2sql.sql_dialect import (
    DB_TYPE_MYSQL,
    normalize_db_type,
    transpile_for_execution,
)


class Text2SQLEnumHintService:
    """从候选表中抽样枚举值，生成补充提示词。"""

    def __init__(
        self,
        engine_provider: Callable[[Session], Engine],
        schema_service: Text2SQLSchemaService,
        db_type_provider: Callable[[Session], str] | None = None,
    ):
        self._engine_provider = engine_provider
        self._schema_service = schema_service
        self._db_type_provider = db_type_provider
        self._logger = logging.getLogger("text2sql.console")

    def _resolve_db_type(self, db: Session) -> str:
        """解析当前连接库类型；无提供器或失败时回退 MySQL。"""
        if self._db_type_provider is None:
            return DB_TYPE_MYSQL
        try:
            return normalize_db_type(self._db_type_provider(db))
        except Exception:  # noqa: BLE001
            return DB_TYPE_MYSQL

    @staticmethod
    def _normalize_identifier(value: str | None) -> str:
        text_value = (value or "").strip().strip("`").strip('"')
        if "." in text_value:
            text_value = text_value.split(".")[-1]
        return text_value.lower()

    @staticmethod
    def _normalize_type_name(type_name: str | None) -> str:
        text_value = str(type_name or "").strip().lower()
        if "(" in text_value:
            text_value = text_value.split("(", 1)[0].strip()
        return text_value

    @classmethod
    def _is_enum_candidate_type(cls, type_name: str | None) -> bool:
        # 覆盖 MySQL 与 SQL Server 的「像枚举」类型：n/var/char 文本、tinyint、SQL Server 的 bit。
        normalized = cls._normalize_type_name(type_name)
        return normalized in {"varchar", "char", "tinyint", "nvarchar", "nchar", "bit"}

    @classmethod
    def _is_text_like_type(cls, type_name: str | None) -> bool:
        normalized = cls._normalize_type_name(type_name)
        return normalized in {"varchar", "char", "nvarchar", "nchar"}

    @classmethod
    def _is_id_column(cls, column_name: str) -> bool:
        normalized = cls._normalize_identifier(column_name)
        return normalized == "id" or normalized.endswith("_id")

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        safe = str(identifier or "").replace("`", "``")
        return f"`{safe}`"

    @classmethod
    def _select_probe_columns(
        cls,
        columns: list[dict[str, Any]],
        *,
        max_columns: int,
    ) -> list[dict[str, Any]]:
        """从表字段中挑选「值得探测枚举值」的列：枚举候选类型、且排除主键与 id/*_id 列。"""
        candidates: list[dict[str, Any]] = []
        for column in columns:
            column_name = str(column.get("name") or "").strip()
            column_type = str(column.get("type") or "").strip()
            if not column_name or not cls._is_enum_candidate_type(column_type):
                continue
            if bool(column.get("is_primary_key")) or cls._is_id_column(column_name):
                continue
            candidates.append(
                {
                    "name": column_name,
                    "type": column_type,
                }
            )
        return candidates[: max(0, int(max_columns))]

    @classmethod
    def _build_probe_sql(
        cls,
        *,
        table_name: str,
        column_name: str,
        column_type: str,
        primary_key_column: str | None,
        sample_rows: int,
        top_values: int,
    ) -> str:
        """构造探测 SQL：先按主键顺序抽样若干行，再按出现频次取该列 Top-N 高频取值。"""
        quoted_table = cls._quote_identifier(table_name)
        quoted_column = cls._quote_identifier(column_name)
        if cls._is_text_like_type(column_type):
            where_clause = f"{quoted_column} IS NOT NULL AND TRIM({quoted_column}) <> ''"
        else:
            where_clause = f"{quoted_column} IS NOT NULL"

        inner_sql = f"SELECT {quoted_column} AS v FROM {quoted_table} WHERE {where_clause}"
        if primary_key_column:
            inner_sql += f" ORDER BY {cls._quote_identifier(primary_key_column)} ASC"
        inner_sql += f" LIMIT {max(1, int(sample_rows))}"

        return (
            "SELECT v, COUNT(1) AS c "
            f"FROM ({inner_sql}) sampled "
            "GROUP BY v "
            "ORDER BY c DESC "
            f"LIMIT {max(1, int(top_values))}"
        )

    @staticmethod
    def _normalize_probe_rows(
        rows,
        *,
        is_text_column: bool,
        top_values: int,
    ) -> list[tuple[str, int]]:
        value_to_count: dict[str, int] = {}
        for row in rows:
            raw_value = row[0] if len(row) > 0 else None
            raw_count = row[1] if len(row) > 1 else 0
            if raw_value is None:
                continue
            if isinstance(raw_value, bytes):
                raw_value = raw_value.decode("utf-8", errors="replace")

            normalized_value = str(raw_value).strip()
            if is_text_column and not normalized_value:
                continue
            if not normalized_value:
                continue

            try:
                normalized_count = int(raw_count or 0)
            except (TypeError, ValueError):
                normalized_count = 0
            if normalized_count <= 0:
                continue

            previous = value_to_count.get(normalized_value)
            if previous is None or normalized_count > previous:
                value_to_count[normalized_value] = normalized_count

        ranked = sorted(value_to_count.items(), key=lambda item: (-item[1], item[0]))
        return ranked[: max(1, int(top_values))]

    @staticmethod
    def _is_timeout_error(exc: Exception) -> bool:
        message = str(exc).lower()
        timeout_signals = (
            "max_execution_time",
            "execution was interrupted",
            "query timeout",
            "statement timeout",
            "canceling statement",
        )
        return any(token in message for token in timeout_signals)

    @classmethod
    def _extract_primary_key_column(cls, columns: list[dict[str, Any]]) -> str | None:
        for column in columns:
            if bool(column.get("is_primary_key")):
                column_name = str(column.get("name") or "").strip()
                if column_name:
                    return column_name
        return None

    def _probe_single_column(
        self,
        *,
        engine: Engine,
        table_name: str,
        column_name: str,
        column_type: str,
        primary_key_column: str | None,
        sample_rows: int,
        top_values: int,
        timeout_ms: int,
        db_type: str = DB_TYPE_MYSQL,
    ) -> dict[str, Any]:
        # 探测 SQL 以 MySQL 方言构造，执行前按目标库类型转写（如 SQL Server 的 LIMIT→TOP、反引号→[]）。
        sql = self._build_probe_sql(
            table_name=table_name,
            column_name=column_name,
            column_type=column_type,
            primary_key_column=primary_key_column,
            sample_rows=sample_rows,
            top_values=top_values,
        )
        sql = transpile_for_execution(sql, db_type)
        try:
            with engine.connect() as conn:
                try:
                    conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME={max(1, int(timeout_ms))}"))
                except Exception:  # noqa: BLE001
                    pass
                result = conn.execute(text(sql))
                values = self._normalize_probe_rows(
                    result.fetchall(),
                    is_text_column=self._is_text_like_type(column_type),
                    top_values=top_values,
                )
                return {
                    "table_name": table_name,
                    "column_name": column_name,
                    "values": values,
                    "timeout": False,
                    "error": False,
                }
        except Exception as exc:  # noqa: BLE001
            return {
                "table_name": table_name,
                "column_name": column_name,
                "values": [],
                "timeout": self._is_timeout_error(exc),
                "error": True,
            }

    @staticmethod
    def _build_values_payload(hint_map: dict[str, dict[str, list[tuple[str, int]]]]) -> dict[str, dict[str, list[str]]]:
        payload: dict[str, dict[str, list[str]]] = {}
        for table_name, columns in hint_map.items():
            column_payload: dict[str, list[str]] = {}
            for column_name, values in columns.items():
                compact_values = [str(item[0]) for item in values if str(item[0]).strip()]
                if compact_values:
                    column_payload[column_name] = compact_values
            if column_payload:
                payload[table_name] = column_payload
        return payload

    @classmethod
    def _render_enum_hint_json(cls, hint_map: dict[str, dict[str, list[tuple[str, int]]]]) -> str:
        payload = {"enum_hints": cls._build_values_payload(hint_map)}
        return json.dumps(payload, ensure_ascii=False)

    @classmethod
    def _append_hint_block(cls, base_prompt_hint: str, hint_map: dict[str, dict[str, list[tuple[str, int]]]]) -> str:
        json_text = cls._render_enum_hint_json(hint_map)
        block = f"enum_hints_json:\n{json_text}"
        base = str(base_prompt_hint or "").strip()
        if not base:
            return block
        return f"{base}\n\n{block}"

    @classmethod
    def _trim_hint_map_for_prompt(
        cls,
        *,
        base_prompt_hint: str,
        hint_map: dict[str, dict[str, list[tuple[str, int]]]],
        max_prompt_chars: int,
    ) -> dict[str, dict[str, list[tuple[str, int]]]]:
        """按提示词字符上限裁剪枚举提示：优先丢弃低频取值，再不够则整列剔除，控制 token 占用。"""
        if max_prompt_chars <= 0:
            return {}

        if len(str(base_prompt_hint or "")) >= max_prompt_chars:
            return {}

        working: dict[str, dict[str, list[tuple[str, int]]]] = {
            table_name: {column_name: list(values) for column_name, values in columns.items()}
            for table_name, columns in hint_map.items()
            if columns
        }

        while working and len(cls._append_hint_block(base_prompt_hint, working)) > max_prompt_chars:
            removable_values: list[tuple[int, str, str]] = []
            for table_name, columns in working.items():
                for column_name, values in columns.items():
                    if len(values) > 1:
                        removable_values.append((int(values[-1][1]), table_name, column_name))

            if removable_values:
                removable_values.sort(key=lambda item: (item[0], item[1], item[2]))
                _, table_name, column_name = removable_values[0]
                working[table_name][column_name].pop()
                continue

            removable_fields: list[tuple[int, str, str]] = []
            for table_name, columns in working.items():
                for column_name, values in columns.items():
                    if not values:
                        continue
                    removable_fields.append((int(values[0][1]), table_name, column_name))

            if not removable_fields:
                break

            removable_fields.sort(key=lambda item: (item[0], item[1], item[2]))
            _, table_name, column_name = removable_fields[0]
            del working[table_name][column_name]
            if not working[table_name]:
                del working[table_name]

        return working

    def build_prompt_hint(
        self,
        *,
        db: Session,
        candidate_tables: list[str],
        queryable_columns_map: dict[str, set[str]] | None,
        base_prompt_hint: str,
    ) -> str:
        """对外入口：探测候选表枚举字段的高频取值，并把 enum_hints_json 追加到 base_prompt_hint。

        受多项配置约束（最多探测表数/列数/取值数、采样行数、超时、并发数、提示词字符上限），
        全程异常/超时安全降级为原始提示词，绝不阻断主流程。
        """
        start_ns = time.monotonic_ns()
        table_limit = max(1, int(settings.TEXT2SQL_ENUM_HINT_MAX_TABLES))
        sample_rows = max(1, int(settings.TEXT2SQL_ENUM_HINT_SAMPLE_ROWS))
        top_values = max(1, int(settings.TEXT2SQL_ENUM_HINT_TOP_VALUES))
        max_columns = max(1, int(settings.TEXT2SQL_ENUM_HINT_MAX_COLUMNS_PER_TABLE))
        max_workers = max(1, int(settings.TEXT2SQL_ENUM_HINT_MAX_WORKERS))
        timeout_ms = max(1, int(settings.TEXT2SQL_ENUM_HINT_PROBE_TIMEOUT_MS))
        max_prompt_chars = max(1, int(settings.TEXT2SQL_ENUM_HINT_MAX_PROMPT_CHARS))

        selected_tables: list[str] = []
        seen_tables: set[str] = set()
        for raw_table in candidate_tables:
            table_name = str(raw_table or "").strip()
            if not table_name:
                continue
            normalized = self._normalize_identifier(table_name)
            if not normalized or normalized in seen_tables:
                continue
            seen_tables.add(normalized)
            selected_tables.append(table_name)
            if len(selected_tables) >= table_limit:
                break

        if not selected_tables:
            return str(base_prompt_hint or "")

        degraded = False
        timeout_fields = 0
        hit_fields = 0
        probe_fields = 0

        try:
            metadata_map = self._schema_service.get_live_table_column_metadata(
                db,
                table_names=selected_tables,
                queryable_columns_map=queryable_columns_map,
            )
            engine = self._engine_provider(db)
            db_type = self._resolve_db_type(db)
            probe_tasks: list[dict[str, str]] = []
            for table_name in selected_tables:
                table_columns = metadata_map.get(table_name, [])
                primary_key_column = self._extract_primary_key_column(table_columns)
                for column in self._select_probe_columns(table_columns, max_columns=max_columns):
                    probe_tasks.append(
                        {
                            "table_name": table_name,
                            "column_name": str(column.get("name") or ""),
                            "column_type": str(column.get("type") or ""),
                            "primary_key_column": primary_key_column or "",
                        }
                    )

            probe_fields = len(probe_tasks)
            if not probe_tasks:
                return str(base_prompt_hint or "")

            hint_map: dict[str, dict[str, list[tuple[str, int]]]] = {}
            workers = min(max_workers, len(probe_tasks))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_map = {
                    executor.submit(
                        self._probe_single_column,
                        engine=engine,
                        table_name=task["table_name"],
                        column_name=task["column_name"],
                        column_type=task["column_type"],
                        primary_key_column=task["primary_key_column"] or None,
                        sample_rows=sample_rows,
                        top_values=top_values,
                        timeout_ms=timeout_ms,
                        db_type=db_type,
                    ): task
                    for task in probe_tasks
                }
                for future in as_completed(future_map):
                    result = future.result()
                    if bool(result.get("error")):
                        degraded = True
                    if bool(result.get("timeout")):
                        timeout_fields += 1

                    values = result.get("values") or []
                    if not values:
                        continue

                    table_name = str(result.get("table_name") or "")
                    column_name = str(result.get("column_name") or "")
                    if not table_name or not column_name:
                        continue
                    hint_map.setdefault(table_name, {})[column_name] = list(values)

            hit_fields = sum(len(columns) for columns in hint_map.values())
            if not hint_map:
                return str(base_prompt_hint or "")

            trimmed_hint_map = self._trim_hint_map_for_prompt(
                base_prompt_hint=str(base_prompt_hint or ""),
                hint_map=hint_map,
                max_prompt_chars=max_prompt_chars,
            )
            if not trimmed_hint_map:
                degraded = True
                return str(base_prompt_hint or "")
            return self._append_hint_block(str(base_prompt_hint or ""), trimmed_hint_map)
        except Exception:  # noqa: BLE001
            degraded = True
            return str(base_prompt_hint or "")
        finally:
            duration_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
            self._logger.info(
                "[enum_hint] tables=%s probed_fields=%s hit_fields=%s timeout_fields=%s duration_ms=%s degraded=%s",
                json.dumps(selected_tables, ensure_ascii=False),
                probe_fields,
                hit_fields,
                timeout_fields,
                duration_ms,
                degraded,
            )
