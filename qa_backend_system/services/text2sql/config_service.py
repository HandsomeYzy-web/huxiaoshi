"""Text2SQL 用户配置服务。

管理「某用户在某个数据库连接下」选了哪些表、自定义了什么业务 prompt 提示，
并按「连接 + 用户」二维隔离配置：切换连接后配置互不串台。
为兼容历史数据，读取时优先取按连接隔离的 scoped 配置，回退到旧版（仅按用户）的配置。
对外还提供 get_runtime_config，把配置整理成流水线运行所需的精简结构。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from repositories.text2sql_config_repo import Text2SQLConfigRepository
from repositories.text2sql_scoped_config_repo import Text2SQLScopedConfigRepository
from models.schemas.text2sql_schema import Text2SQLConfigResponse, Text2SQLConnectionResponse, UpdateText2SQLConfigRequest
from services.text2sql.connection_service import Text2SQLConnectionService
from services.text2sql.schema_service import Text2SQLSchemaService

_UNCONFIGURED_CONNECTION_KEY = "unconfigured"


class Text2SQLConfigService:
    """管理表/prompt 配置，并按「连接 + 用户」二维隔离。"""

    def __init__(
        self,
        schema_service: Text2SQLSchemaService,
        connection_service: Text2SQLConnectionService,
    ):
        self.schema_service = schema_service
        self.connection_service = connection_service

    @staticmethod
    def _resolve_user_id(user_id: int | None) -> int:
        return max(1, int(user_id or 1))

    @staticmethod
    def _safe_loads(raw: str | None, default: list[str]) -> list[str]:
        if not raw:
            return default
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return default
        if not isinstance(parsed, list):
            return default
        return [str(item) for item in parsed]

    @staticmethod
    def _normalize_selected_tables(selected_tables: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in selected_tables:
            table_name = str(item).strip()
            if not table_name:
                continue
            key = table_name.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(table_name)
        return cleaned

    @staticmethod
    def _normalize_key_part(value: Any) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _build_connection_key(cls, connection: Text2SQLConnectionResponse) -> str:
        """由连接关键参数（类型/主机/端口/库/用户）拼成稳定的连接标识，作为配置隔离维度。

        未配置连接时统一归到 "unconfigured" 桶，避免空连接污染正常配置。
        """
        if not connection.configured:
            return _UNCONFIGURED_CONNECTION_KEY
        return "|".join(
            [
                cls._normalize_key_part(connection.db_type or "mysql"),
                cls._normalize_key_part(connection.host),
                str(int(connection.port or 3306)),
                cls._normalize_key_part(connection.database),
                cls._normalize_key_part(connection.username),
            ]
        )

    def _get_active_connection_key(self, db: Session) -> str:
        connection = self.connection_service.get_public_connection(db)
        return self._build_connection_key(connection)

    def get_connection_key(self, db: Session, user_id: int | None = None) -> str:
        _ = self._resolve_user_id(user_id)
        return self._get_active_connection_key(db)

    @staticmethod
    def _build_response(config_record) -> Text2SQLConfigResponse:
        if not config_record:
            return Text2SQLConfigResponse()
        selected_tables = Text2SQLConfigService._safe_loads(config_record.selected_tables, [])
        selected_tables = Text2SQLConfigService._normalize_selected_tables(selected_tables)
        return Text2SQLConfigResponse(
            selected_tables=selected_tables,
            prompt_hint=config_record.prompt_hint or "",
        )

    def _get_scoped_or_legacy_config_record(self, db: Session, user_id: int | None = None):
        """读取配置记录：优先按「用户+连接」隔离的 scoped 配置，回退到旧版按用户的配置。"""
        resolved_user_id = self._resolve_user_id(user_id)
        connection_key = self._get_active_connection_key(db)
        scoped_config = Text2SQLScopedConfigRepository(db).get_by_user_and_connection(
            resolved_user_id,
            connection_key,
        )
        if scoped_config:
            return scoped_config
        return Text2SQLConfigRepository(db).get_by_user_id(resolved_user_id)

    def get_config(self, db: Session, user_id: int | None = None) -> Text2SQLConfigResponse:
        """获取用户配置；从未配置过时，默认放开当前连接下的全部表。"""
        config_record = self._get_scoped_or_legacy_config_record(db, user_id=user_id)
        if config_record:
            return self._build_response(config_record)

        try:
            default_tables = self.schema_service.list_table_names(db)
        except Exception:  # noqa: BLE001
            default_tables = []
        return Text2SQLConfigResponse(
            selected_tables=default_tables,
            prompt_hint="",
        )

    def update_config(
        self,
        db: Session,
        request: UpdateText2SQLConfigRequest,
        user_id: int | None = None,
    ) -> Text2SQLConfigResponse:
        """更新用户在当前连接下的选表与 prompt：先校验所选表确实存在，再按连接维度 upsert。"""
        resolved_user_id = self._resolve_user_id(user_id)
        selected_tables = self._normalize_selected_tables(request.selected_tables)
        if selected_tables:
            resolved_tables, missing_tables = self.schema_service.validate_selected_tables(db, selected_tables)
        else:
            resolved_tables, missing_tables = [], []
        if missing_tables:
            raise ValueError(f"Selected tables are not present in current database schema: {', '.join(missing_tables)}")
        prompt_hint = (request.prompt_hint or "").strip()
        connection_key = self._get_active_connection_key(db)
        Text2SQLScopedConfigRepository(db).upsert(
            user_id=resolved_user_id,
            connection_key=connection_key,
            selected_tables=json.dumps(resolved_tables, ensure_ascii=False),
            prompt_hint=prompt_hint,
        )
        return self.get_config(db, user_id=resolved_user_id)

    def get_runtime_config(self, db: Session, user_id: int | None = None) -> dict:
        """把用户配置整理成流水线运行所需的精简结构（选表 + prompt 提示）。"""
        config = self.get_config(db, user_id=user_id)
        return {
            "selected_tables": config.selected_tables,
            "prompt_hint": config.prompt_hint,
        }
