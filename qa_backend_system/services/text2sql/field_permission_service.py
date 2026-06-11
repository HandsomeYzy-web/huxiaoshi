"""Text2SQL 表级 / 字段级查询权限服务。

控制「某用户在某连接下」哪些表、哪些字段可以被 Text2SQL 查询，是数据可见性的最后一道边界：
- 权限同样按「用户 + 连接」隔离（连接键过长时退化为哈希）；
- 采用「默认放开」语义：未显式配置过的表/字段视为可查，只有被显式关闭的才不可查；
- get_queryable_table_names / get_queryable_columns_map 的结果会贯穿到表路由、SQL 生成与校验，
  确保越权字段从一开始就不进入候选；
- build_query_field_comment_bindings 还负责把结果列回贴数据库表/字段注释，供前端展示字段业务含义。
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from repositories.text2sql_field_permission_repo import Text2SQLFieldPermissionRepository
from models.schemas.text2sql_schema import (
    Text2SQLTableFieldItem,
    Text2SQLTableFieldsResponse,
    Text2SQLTableOption,
    Text2SQLTableOptionsResponse,
    UpdateText2SQLTableFieldsRequest,
)
from services.text2sql.config_service import Text2SQLConfigService
from services.text2sql.schema_service import Text2SQLSchemaService

class Text2SQLFieldPermissionService:
    """管理表/字段级查询开关，并提供字段绑定能力。"""
    def __init__(
        self,
        schema_service: Text2SQLSchemaService,
        config_service: Text2SQLConfigService,
    ):
        """初始化字段权限服务依赖。"""
        self.schema_service = schema_service
        self.config_service = config_service

    @staticmethod
    def _resolve_user_id(user_id: int | None) -> int:
        return max(1, int(user_id or 1))

    def _get_connection_key(self, db: Session, user_id: int) -> str:
        try:
            return self.config_service.get_connection_key(db, user_id)
        except TypeError:
            # backward compatibility for tests/mocks that still expose old signature
            return self.config_service.get_connection_key(db)

    @staticmethod
    def _normalize_identifier(value: str | None) -> str:
        """标准化标识符，便于大小写无关比较。"""
        text = (value or "").strip().strip("`").strip('"')
        if "." in text:
            text = text.split(".")[-1]
        return text.lower()

    @staticmethod
    def _normalize_connection_key(value: str | None) -> str:
        """标准化连接键，过长时退化为哈希值。"""
        text = str(value or "").strip()
        if len(text) <= 255:
            return text
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def _resolve_table_name(self, db: Session, table_name: str) -> str:
        """校验并返回数据库中的真实表名。"""
        resolved, missing = self.schema_service.validate_selected_tables(db, [table_name])
        if missing or not resolved:
            raise ValueError(f"\u4ee5\u4e0b\u8868\u5728\u6570\u636e\u5e93\u4e2d\u4e0d\u5b58\u5728: {table_name}")
        return resolved[0]

    def get_table_options(self, db: Session) -> Text2SQLTableOptionsResponse:
        """返回可配置字段权限的表列表。"""
        options = self.schema_service.list_table_options(db)
        return Text2SQLTableOptionsResponse(tables=[Text2SQLTableOption(**item) for item in options])

    def get_table_fields(
        self,
        db: Session,
        table_name: str,
        user_id: int | None = None,
    ) -> Text2SQLTableFieldsResponse:
        """读取指定表的字段清单及开关状态。"""
        resolved_user_id = self._resolve_user_id(user_id)
        resolved_table = self._resolve_table_name(db, table_name)
        table_detail = self.schema_service.get_table_detail(db, resolved_table)
        connection_key = self._normalize_connection_key(self._get_connection_key(db, resolved_user_id))
        records = Text2SQLFieldPermissionRepository(db).list_by_user_and_connection(
            resolved_user_id,
            connection_key,
            resolved_table,
        )
        enabled_lookup = {
            self._normalize_identifier(record.column_name): bool(record.query_enabled)
            for record in records
        }
        fields: list[Text2SQLTableFieldItem] = []
        for column in table_detail.get("columns", []):
            column_name = str(column.get("name") or "")
            if not column_name:
                continue
            fields.append(
                Text2SQLTableFieldItem(
                    name=column_name,
                    type=str(column.get("type") or ""),
                    comment=str(column.get("comment") or ""),
                    query_enabled=enabled_lookup.get(self._normalize_identifier(column_name), True),
                )
            )
        return Text2SQLTableFieldsResponse(
            table_name=resolved_table,
            table_comment=str(table_detail.get("table_comment") or ""),
            fields=fields,
        )

    def update_table_fields(
        self,
        db: Session,
        table_name: str,
        request: UpdateText2SQLTableFieldsRequest,
        user_id: int | None = None,
    ) -> Text2SQLTableFieldsResponse:
        """更新指定表的字段开关配置。"""
        resolved_user_id = self._resolve_user_id(user_id)
        resolved_table = self._resolve_table_name(db, table_name)
        table_detail = self.schema_service.get_table_detail(db, resolved_table)
        column_name_lookup = {
            self._normalize_identifier(str(column.get("name") or "")): str(column.get("name") or "")
            for column in table_detail.get("columns", [])
            if str(column.get("name") or "")
        }
        if not column_name_lookup:
            raise ValueError(f"\u6570\u636e\u8868 {resolved_table} \u6ca1\u6709\u53ef\u914d\u7f6e\u5b57\u6bb5")
        incoming_map: dict[str, bool] = {}
        for field in request.fields:
            normalized = self._normalize_identifier(field.name)
            real_name = column_name_lookup.get(normalized)
            if not real_name:
                raise ValueError(f"\u5b57\u6bb5\u4e0d\u5b58\u5728: {field.name}")
            incoming_map[normalized] = bool(field.query_enabled)
        permissions: dict[str, bool] = {}
        for normalized, real_name in column_name_lookup.items():
            permissions[real_name] = incoming_map.get(normalized, True)
        if not any(permissions.values()):
            raise ValueError("\u81f3\u5c11\u4fdd\u7559\u4e00\u4e2a\u53ef\u67e5\u8be2\u5b57\u6bb5")
        connection_key = self._normalize_connection_key(self._get_connection_key(db, resolved_user_id))
        Text2SQLFieldPermissionRepository(db).replace_table_permissions(
            user_id=resolved_user_id,
            connection_key=connection_key,
            table_name=resolved_table,
            permissions=permissions,
        )
        return self.get_table_fields(db, resolved_table, user_id=resolved_user_id)

    def get_queryable_columns_map(
        self,
        db: Session,
        table_names: list[str] | None = None,
        user_id: int | None = None,
    ) -> dict[str, set[str]]:
        """返回每张表当前允许查询的字段集合。"""
        resolved_user_id = self._resolve_user_id(user_id)
        resolved_tables = self.get_queryable_table_names(db, table_names, user_id=resolved_user_id)
        if not resolved_tables:
            return {}
        schema = self.schema_service.list_schema_overview(db, resolved_tables)
        connection_key = self._normalize_connection_key(self._get_connection_key(db, resolved_user_id))
        records = Text2SQLFieldPermissionRepository(db).list_by_user_and_connection(
            resolved_user_id,
            connection_key,
        )
        permission_lookup: dict[str, dict[str, bool]] = {}
        for record in records:
            normalized_table = self._normalize_identifier(record.table_name)
            normalized_column = self._normalize_identifier(record.column_name)
            permission_lookup.setdefault(normalized_table, {})[normalized_column] = bool(record.query_enabled)
        result: dict[str, set[str]] = {}
        for table in schema.tables:
            normalized_table = self._normalize_identifier(table.table_name)
            table_permission = permission_lookup.get(normalized_table, {})
            enabled_columns: set[str] = set()
            for column in table.columns:
                normalized_column = self._normalize_identifier(column.name)
                if table_permission.get(normalized_column, True):
                    enabled_columns.add(column.name)
            if enabled_columns:
                result[table.table_name] = enabled_columns
        return result

    def get_queryable_table_names(
        self,
        db: Session,
        table_names: list[str] | None = None,
        user_id: int | None = None,
    ) -> list[str]:
        """返回当前权限配置下可查询的表名列表。"""
        resolved_user_id = self._resolve_user_id(user_id)
        if table_names is None:
            resolved_tables = self.schema_service.list_table_names(db)
        else:
            resolved_tables, _ = self.schema_service.validate_selected_tables(db, table_names)
        if not resolved_tables:
            return []

        normalized_lookup = {self._normalize_identifier(table_name): table_name for table_name in resolved_tables}
        connection_key = self._normalize_connection_key(self._get_connection_key(db, resolved_user_id))
        records = Text2SQLFieldPermissionRepository(db).list_by_user_and_connection(
            resolved_user_id,
            connection_key,
        )

        has_records: dict[str, bool] = {}
        has_enabled: dict[str, bool] = {}
        for record in records:
            normalized_table = self._normalize_identifier(record.table_name)
            if normalized_table not in normalized_lookup:
                continue
            has_records[normalized_table] = True
            if bool(record.query_enabled):
                has_enabled[normalized_table] = True

        # 「默认放开」语义：没有任何权限记录的表视为可查；有记录则必须至少启用一个字段才可查。
        queryable_tables: list[str] = []
        for table_name in resolved_tables:
            normalized_table = self._normalize_identifier(table_name)
            if not has_records.get(normalized_table, False):
                queryable_tables.append(table_name)
                continue
            if has_enabled.get(normalized_table, False):
                queryable_tables.append(table_name)
        return queryable_tables

    @staticmethod
    def _pick_best_comment_match(matches: list[dict[str, str]]) -> dict[str, str]:
        """从多个候选注释里挑出信息最完整的一条。"""
        if not matches:
            return {}
        ranked = sorted(
            matches,
            key=lambda item: (
                bool(str(item.get("column_comment") or "").strip()),
                bool(str(item.get("table_comment") or "").strip()),
                str(item.get("table_name") or ""),
                str(item.get("column_name") or ""),
            ),
            reverse=True,
        )
        return ranked[0]

    def build_query_field_comment_bindings(
        self,
        db: Session,
        columns: list[str],
        table_names: list[str] | None,
        queryable_columns_map: dict[str, set[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """把查询结果字段映射到数据库表/字段注释，供前端展示字段语义。"""
        if not columns:
            return []

        normalized_tables = [str(table).strip() for table in (table_names or []) if str(table).strip()]
        schema_lookup: dict[str, list[dict[str, str]]] = {}
        if normalized_tables:
            try:
                schema = self.schema_service.list_schema_overview(
                    db,
                    table_names=normalized_tables,
                    queryable_columns_map=queryable_columns_map,
                )
                for table in schema.tables:
                    table_name = str(table.table_name or "")
                    table_comment = str(table.table_comment or "")
                    for column in table.columns:
                        column_name = str(column.name or "")
                        if not column_name:
                            continue
                        normalized_column = self._normalize_identifier(column_name)
                        if not normalized_column:
                            continue
                        schema_lookup.setdefault(normalized_column, []).append(
                            {
                                "table_name": table_name,
                                "table_comment": table_comment,
                                "column_name": column_name,
                                "column_comment": str(column.comment or ""),
                            }
                        )
            except Exception:  # noqa: BLE001
                schema_lookup = {}

        bindings: list[dict[str, Any]] = []
        for raw_column in columns:
            column = str(raw_column or "").strip()
            if not column:
                continue
            normalized_column = self._normalize_identifier(column)
            matches = schema_lookup.get(normalized_column, [])
            chosen = self._pick_best_comment_match(matches)

            table_name = str(chosen.get("table_name") or "")
            table_comment = str(chosen.get("table_comment") or "")
            source_column = str(chosen.get("column_name") or column)
            column_comment = str(chosen.get("column_comment") or "")
            inferred_meaning = column_comment or table_comment or column
            confidence = 1.0 if (column_comment or table_comment) else 0.0

            if matches and len(matches) > 1:
                candidate_tables = "、".join(
                    sorted({str(item.get("table_name") or "") for item in matches if str(item.get("table_name") or "")})
                )
                reason = f"字段在多个表命中（{candidate_tables}），按注释完整度绑定到 {table_name}.{source_column}"
            elif matches:
                reason = f"已绑定数据库注释：{table_name}.{source_column}"
            else:
                reason = "未命中数据库字段注释，返回字段原名"

            bindings.append(
                {
                    "column": column,
                    "inferred_meaning": inferred_meaning,
                    "confidence": confidence,
                    "reason": reason,
                    "table_name": table_name,
                    "table_comment": table_comment,
                    "column_name": source_column,
                    "column_comment": column_comment,
                }
            )
        return bindings

