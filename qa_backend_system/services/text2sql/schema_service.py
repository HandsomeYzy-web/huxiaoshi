"""Text2SQL 实时表结构（Schema）服务。

通过 SQLAlchemy Inspector 直接读取「被查询业务库」的实时元数据：表名、表注释、字段名、
字段类型、字段注释、主键等。这些元数据是表路由打分、SQL 生成提示词、SELECT * 展开、
字段权限校验的共同数据源。

关键能力：
- 校验用户所选表是否真实存在（validate_selected_tables）；
- 叠加「字段权限」过滤，只暴露用户有权查询的列（queryable_columns_map）；
- build_live_schema_json 把结构序列化为喂给大模型的 JSON，并可按问题相关度做「列剪枝」，
  控制提示词长度（仅在带 question 时启用，避免修复路径误删必需字段）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from core.config import settings
from models.schemas.text2sql_schema import Text2SQLSchemaResponse
from services.text2sql.connection_service import Text2SQLConnectionService
from services.text2sql.text_tokens import build_search_tokens


class Text2SQLSchemaService:
    """读取实时数据库结构，为 Text2SQL 提供表/字段元数据。"""

    def __init__(self, connection_service: Text2SQLConnectionService):
        self.connection_service = connection_service

    @staticmethod
    def _normalize_identifier(value: str | None) -> str:
        text = (value or "").strip().strip("`").strip('"')
        if "." in text:
            text = text.split(".")[-1]
        return text.lower()

    @staticmethod
    def _safe_text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_queryable_columns_map(
        cls,
        queryable_columns_map: dict[str, set[str]] | None,
    ) -> dict[str, set[str]]:
        normalized: dict[str, set[str]] = {}
        for table_name, columns in (queryable_columns_map or {}).items():
            normalized_table = cls._normalize_identifier(table_name)
            if not normalized_table:
                continue
            normalized[normalized_table] = {
                cls._normalize_identifier(column_name)
                for column_name in (columns or set())
                if cls._normalize_identifier(column_name)
            }
        return normalized

    @classmethod
    def _extract_table_comment(cls, inspector, table_name: str) -> str:
        try:
            payload = inspector.get_table_comment(table_name)
        except Exception:  # noqa: BLE001
            return ""
        if isinstance(payload, dict):
            return cls._safe_text(payload.get("text") or payload.get("comment"))
        return cls._safe_text(payload)

    @classmethod
    def _extract_column_comment(cls, payload: dict[str, Any]) -> str:
        return cls._safe_text(payload.get("comment"))

    @classmethod
    def _extract_primary_key_columns(cls, inspector, table_name: str) -> set[str]:
        try:
            payload = inspector.get_pk_constraint(table_name) or {}
        except Exception:  # noqa: BLE001
            return set()
        raw_columns = payload.get("constrained_columns") if isinstance(payload, dict) else []
        primary_keys: set[str] = set()
        for raw_name in (raw_columns or []):
            normalized = cls._normalize_identifier(cls._safe_text(raw_name))
            if normalized:
                primary_keys.add(normalized)
        return primary_keys

    @classmethod
    def _resolve_target_tables(
        cls,
        all_tables: list[str],
        table_names: list[str] | None,
    ) -> tuple[list[str], list[str]]:
        """把请求表名对齐到库中真实表名，返回（命中的真实表名, 库中不存在的表名）。

        table_names 为 None 表示「全部表」；为空列表表示「不选任何表」。
        对齐时忽略大小写/反引号/库名前缀，便于容错。
        """
        if table_names is None:
            return sorted(all_tables), []
        if len(table_names) == 0:
            return [], []

        table_lookup = {cls._normalize_identifier(name): name for name in all_tables}
        resolved_tables: list[str] = []
        missing_tables: list[str] = []
        seen: set[str] = set()

        for raw_name in table_names:
            normalized = cls._normalize_identifier(raw_name)
            real_name = table_lookup.get(normalized)
            if not real_name:
                missing_tables.append(str(raw_name))
                continue
            if real_name in seen:
                continue
            seen.add(real_name)
            resolved_tables.append(real_name)
        return resolved_tables, missing_tables

    def list_schema_overview(
        self,
        db: Session,
        table_names: list[str] | None = None,
        queryable_columns_map: dict[str, set[str]] | None = None,
    ) -> Text2SQLSchemaResponse:
        """返回指定表的结构概览（表注释 + 字段名/类型/注释）。

        传入 queryable_columns_map 时只保留有权查询的字段，从源头做字段级脱敏。
        """
        engine = self.connection_service.get_engine(db)
        inspector = inspect(engine)
        all_tables = inspector.get_table_names()
        resolved_tables, missing_tables = self._resolve_target_tables(all_tables, table_names)
        if table_names and missing_tables:
            raise ValueError(f"以下表在数据库中不存在: {', '.join(missing_tables)}")

        normalized_queryable_map = self._normalize_queryable_columns_map(queryable_columns_map)
        tables: list[dict[str, Any]] = []
        for table_name in resolved_tables:
            normalized_table = self._normalize_identifier(table_name)
            allowed_columns = normalized_queryable_map.get(normalized_table)

            column_items: list[dict[str, str]] = []
            for col in inspector.get_columns(table_name):
                column_name = self._safe_text(col.get("name"))
                if not column_name:
                    continue
                normalized_column = self._normalize_identifier(column_name)
                if allowed_columns is not None and normalized_column not in allowed_columns:
                    continue
                column_items.append(
                    {
                        "name": column_name,
                        "type": self._safe_text(col.get("type")),
                        "comment": self._extract_column_comment(col),
                    }
                )

            tables.append(
                {
                    "table_name": table_name,
                    "table_comment": self._extract_table_comment(inspector, table_name),
                    "columns": column_items,
                }
            )

        return Text2SQLSchemaResponse(tables=tables)

    def list_table_options(self, db: Session) -> list[dict[str, str]]:
        """列出连接下全部表及其表注释（供前端「选表」下拉使用）。"""
        engine = self.connection_service.get_engine(db)
        inspector = inspect(engine)
        table_names = sorted(inspector.get_table_names())
        return [
            {
                "table_name": table_name,
                "table_comment": self._extract_table_comment(inspector, table_name),
            }
            for table_name in table_names
        ]

    def list_table_options_by_names(self, db: Session, table_names: list[str]) -> list[dict[str, str]]:
        """按给定表名批量取「表名 + 表注释」（路由阶段构建候选表画像时用）。"""
        if not table_names:
            return []
        engine = self.connection_service.get_engine(db)
        inspector = inspect(engine)
        all_tables = inspector.get_table_names()
        resolved_tables, missing_tables = self._resolve_target_tables(all_tables, table_names)
        if missing_tables:
            raise ValueError(f"以下表在数据库中不存在: {', '.join(missing_tables)}")
        return [
            {
                "table_name": table_name,
                "table_comment": self._extract_table_comment(inspector, table_name),
            }
            for table_name in resolved_tables
        ]

    def get_table_detail(
        self,
        db: Session,
        table_name: str,
        queryable_columns_map: dict[str, set[str]] | None = None,
    ) -> dict[str, Any]:
        """获取单张表的结构详情（供前端表详情面板使用）。"""
        schema = self.list_schema_overview(
            db,
            table_names=[table_name],
            queryable_columns_map=queryable_columns_map,
        )
        if not schema.tables:
            raise ValueError(f"以下表在数据库中不存在: {table_name}")
        return schema.tables[0].model_dump()

    def list_table_names(self, db: Session) -> list[str]:
        """返回连接下全部表名（已排序）。"""
        engine = self.connection_service.get_engine(db)
        inspector = inspect(engine)
        return sorted(inspector.get_table_names())

    def validate_selected_tables(self, db: Session, table_names: list[str] | None) -> tuple[list[str], list[str]]:
        """校验所选表是否真实存在，返回（命中真实表名, 不存在的表名）。"""
        engine = self.connection_service.get_engine(db)
        inspector = inspect(engine)
        return self._resolve_target_tables(inspector.get_table_names(), table_names)

    def get_live_table_column_metadata(
        self,
        db: Session,
        table_names: list[str] | None = None,
        queryable_columns_map: dict[str, set[str]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """返回 {表名: [{字段名, 类型, 是否主键}]}，并按字段权限过滤（带主键标记，供关系配置等使用）。"""
        engine = self.connection_service.get_engine(db)
        inspector = inspect(engine)
        all_tables = inspector.get_table_names()
        resolved_tables, missing_tables = self._resolve_target_tables(all_tables, table_names)
        if table_names and missing_tables:
            raise ValueError(f"以下表在数据库中不存在: {', '.join(missing_tables)}")

        normalized_queryable_map = self._normalize_queryable_columns_map(queryable_columns_map)
        metadata: dict[str, list[dict[str, Any]]] = {}
        for table_name in resolved_tables:
            normalized_table = self._normalize_identifier(table_name)
            allowed_columns = normalized_queryable_map.get(normalized_table)
            primary_keys = self._extract_primary_key_columns(inspector, table_name)

            column_items: list[dict[str, Any]] = []
            for column in inspector.get_columns(table_name):
                column_name = self._safe_text(column.get("name"))
                if not column_name:
                    continue
                normalized_column = self._normalize_identifier(column_name)
                if allowed_columns is not None and normalized_column not in allowed_columns:
                    continue
                column_items.append(
                    {
                        "name": column_name,
                        "type": self._safe_text(column.get("type")),
                        "is_primary_key": normalized_column in primary_keys,
                    }
                )
            metadata[table_name] = column_items
        return metadata

    def get_live_table_columns_map(
        self,
        db: Session,
        table_names: list[str] | None = None,
        queryable_columns_map: dict[str, set[str]] | None = None,
    ) -> dict[str, set[str]]:
        """返回 {表名: 字段名集合}（权限过滤后），供 SQL 校验、SELECT * 展开等按真实列名比对。"""
        schema = self.list_schema_overview(
            db,
            table_names=table_names,
            queryable_columns_map=queryable_columns_map,
        )
        mapping: dict[str, set[str]] = {}
        for table in schema.tables:
            mapping[table.table_name] = {col.name for col in table.columns}
        return mapping

    def build_live_schema_json(
        self,
        db: Session,
        table_names: list[str] | None = None,
        queryable_columns_map: dict[str, set[str]] | None = None,
        question: str | None = None,
    ) -> str:
        """把表结构序列化成喂给大模型的 JSON 字符串（含表/字段注释）。

        当开启剪枝且带问题文本时，对超宽表只保留与问题最相关的若干列，其余折叠为占位行，
        以压缩提示词、降低 token 成本。
        """
        schema = self.list_schema_overview(
            db,
            table_names=table_names,
            queryable_columns_map=queryable_columns_map,
        )
        # Schema 剪枝仅在“提供了问题文本”时启用，避免修复路径（无 question）误删所需字段。
        question_text = str(question or "").strip()
        prune_enabled = bool(settings.TEXT2SQL_SCHEMA_PRUNE_ENABLED) and bool(question_text)
        max_cols_per_table = max(1, int(settings.TEXT2SQL_SCHEMA_MAX_COLS_PER_TABLE or 1))
        keep_cols = max(1, int(settings.TEXT2SQL_SCHEMA_PRUNE_KEEP_COLS or 1))
        question_tokens = build_search_tokens(question_text, max_tokens=320) if prune_enabled else set()

        tables_payload: list[dict[str, Any]] = []
        for table in schema.tables:
            columns_payload = [
                {
                    "name": col.name,
                    "type": str(col.type or ""),
                    "comment": str(col.comment or ""),
                }
                for col in table.columns
            ]
            if prune_enabled and len(columns_payload) > max_cols_per_table:
                columns_payload = self._prune_columns(columns_payload, question_tokens, keep_cols)
            tables_payload.append(
                {
                    "table_name": table.table_name,
                    "table_comment": table.table_comment,
                    "columns": columns_payload,
                }
            )
        return json.dumps({"tables": tables_payload}, ensure_ascii=False)

    @staticmethod
    def _prune_columns(
        columns_payload: list[dict[str, str]],
        question_tokens: set[str],
        keep_cols: int,
    ) -> list[dict[str, str]]:
        """按“字段名+注释 与问题分词的重叠度”保留最相关的前 keep_cols 列，其余折叠为占位行。"""
        scored: list[tuple[int, int, str, dict[str, str]]] = []
        for column in columns_payload:
            column_name = str(column.get("name") or "")
            column_comment = str(column.get("comment") or "")
            column_tokens = build_search_tokens(f"{column_name} {column_comment}", max_tokens=128)
            overlap = len(column_tokens.intersection(question_tokens))
            has_comment = 1 if column_comment.strip() else 0
            scored.append((overlap, has_comment, column_name, column))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        kept = [item[3] for item in scored[:keep_cols]]
        omitted_count = max(0, len(columns_payload) - len(kept))
        if omitted_count > 0:
            kept.append(
                {
                    "name": f"... 省略 {omitted_count} 列",
                    "type": "schema_pruned",
                    "comment": "schema_pruned_for_prompt",
                }
            )
        return kept
