from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from models.schemas.text2sql_schema import (
    BatchImportText2SQLRelationsRequest,
    ColumnInfo,
    CreateText2SQLRelationRequest,
    Text2SQLRelationBatchImportResponse,
    Text2SQLRelationItem,
    Text2SQLRelationListResponse,
    Text2SQLRelationTableColumnsResponse,
    UpdateText2SQLRelationRequest,
)
from repositories.text2sql_table_relation_repo import Text2SQLTableRelationRepository
from services.text2sql.config_service import Text2SQLConfigService
from services.text2sql.schema_service import Text2SQLSchemaService


class Text2SQLRelationService:
    """管理多表查询的「JOIN 关系白名单」。

    维护「用户 + 连接」维度下、表与表之间允许 JOIN 的字段对（支持复合键、单/批量导入），
    并对外提供两类能力：
    - 管理面：增删改查、批量导入、去重（正反向都算重复）、字段存在性校验；
    - 运行面：get_active_relations_by_tables 把已启用关系整理成「关系提示」，
      供表路由（关系图扩展）与 SQL 校验（JOIN 白名单）使用——大模型只能按这里登记的关系 JOIN，
      从而杜绝凭空关联。所有关系按连接隔离，且操作前校验归属，防止越权访问他人配置。
    """

    def __init__(
        self,
        schema_service: Text2SQLSchemaService,
        config_service: Text2SQLConfigService,
    ):
        self.schema_service = schema_service
        self.config_service = config_service

    @staticmethod
    def _resolve_user_id(user_id: int | None) -> int:
        return max(1, int(user_id or 1))

    def _get_connection_key(self, db: Session, user_id: int) -> str:
        try:
            return self.config_service.get_connection_key(db, user_id)
        except TypeError:
            return self.config_service.get_connection_key(db)

    @staticmethod
    def _normalize_identifier(value: str | None) -> str:
        text = (value or "").strip().strip("`").strip('"')
        if "." in text:
            text = text.split(".")[-1]
        return text.lower()

    @staticmethod
    def _normalize_connection_key(value: str | None) -> str:
        text = str(value or "").strip()
        if len(text) <= 255:
            return text
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @staticmethod
    def _safe_load_columns(raw_value: str | None) -> list[str]:
        if not raw_value:
            return []
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item).strip() for item in parsed if str(item).strip()]

    @classmethod
    def _normalize_columns(cls, columns: list[str]) -> list[str]:
        normalized_columns: list[str] = []
        seen: set[str] = set()
        for raw_column in columns:
            column_name = str(raw_column or "").strip()
            if not column_name:
                continue
            normalized = cls._normalize_identifier(column_name)
            if not normalized:
                continue
            if normalized in seen:
                raise ValueError(f"复合键字段不允许重复: {column_name}")
            seen.add(normalized)
            normalized_columns.append(column_name)
        return normalized_columns

    @classmethod
    def _build_columns_hash(cls, columns: list[str]) -> str:
        normalized = [cls._normalize_identifier(item) for item in columns if cls._normalize_identifier(item)]
        payload = "|".join(normalized)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _format_relation_summary(
        cls,
        source_table: str,
        source_columns: list[str],
        target_table: str,
        target_columns: list[str],
    ) -> str:
        pairs = []
        for source_column, target_column in zip(source_columns, target_columns):
            pairs.append(f"{source_table}.{source_column} = {target_table}.{target_column}")
        return " AND ".join(pairs)

    def _resolve_table_name(self, db: Session, table_name: str) -> str:
        resolved_tables, missing_tables = self.schema_service.validate_selected_tables(db, [table_name])
        if missing_tables or not resolved_tables:
            raise ValueError(f"以下表在数据库中不存在: {table_name}")
        return resolved_tables[0]

    def _resolve_columns(
        self,
        db: Session,
        table_name: str,
        columns: list[str],
    ) -> tuple[str, list[str]]:
        real_table_name = self._resolve_table_name(db, table_name)
        normalized_input_columns = self._normalize_columns(columns)
        if not normalized_input_columns:
            raise ValueError("复合键字段列表不能为空")

        table_detail = self.schema_service.get_table_detail(db, real_table_name)
        lookup = {
            self._normalize_identifier(str(column.get("name") or "")): str(column.get("name") or "")
            for column in table_detail.get("columns", [])
            if str(column.get("name") or "").strip()
        }
        resolved_columns: list[str] = []
        for raw_column in normalized_input_columns:
            normalized = self._normalize_identifier(raw_column)
            real_column = lookup.get(normalized)
            if not real_column:
                raise ValueError(f"字段不存在: {real_table_name}.{raw_column}")
            resolved_columns.append(real_column)
        return real_table_name, resolved_columns

    @classmethod
    def _same_relation(
        cls,
        *,
        source_table: str,
        source_columns: list[str],
        target_table: str,
        target_columns: list[str],
        # 判定两条关系是否等价（大小写无关）；调用方会分别按正向、反向各比一次以识别反向重复。
        other_source_table: str,
        other_source_columns: list[str],
        other_target_table: str,
        other_target_columns: list[str],
    ) -> bool:
        left_source_table = cls._normalize_identifier(source_table)
        left_target_table = cls._normalize_identifier(target_table)
        left_source_columns = tuple(cls._normalize_identifier(item) for item in source_columns)
        left_target_columns = tuple(cls._normalize_identifier(item) for item in target_columns)
        right_source_table = cls._normalize_identifier(other_source_table)
        right_target_table = cls._normalize_identifier(other_target_table)
        right_source_columns = tuple(cls._normalize_identifier(item) for item in other_source_columns)
        right_target_columns = tuple(cls._normalize_identifier(item) for item in other_target_columns)
        return (
            left_source_table == right_source_table
            and left_target_table == right_target_table
            and left_source_columns == right_source_columns
            and left_target_columns == right_target_columns
        )

    def _ensure_no_duplicate_relation(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        source_table: str,
        source_columns: list[str],
        target_table: str,
        target_columns: list[str],
        exclude_id: int | None = None,
    ) -> None:
        """创建/更新前的去重校验：正向或反向命中已有关系即报错（update 时用 exclude_id 排除自身）。"""
        resolved_user_id = self._resolve_user_id(user_id)
        connection_key = self._normalize_connection_key(self._get_connection_key(db, resolved_user_id))
        repo = Text2SQLTableRelationRepository(db)
        existing = repo.list_by_pair(
            user_id=resolved_user_id,
            connection_key=connection_key,
            source_table=source_table,
            target_table=target_table,
            exclude_id=exclude_id,
        )
        for item in existing:
            other_source_columns = self._safe_load_columns(item.source_columns)
            other_target_columns = self._safe_load_columns(item.target_columns)
            if self._same_relation(
                source_table=source_table,
                source_columns=source_columns,
                target_table=target_table,
                target_columns=target_columns,
                other_source_table=item.source_table,
                other_source_columns=other_source_columns,
                other_target_table=item.target_table,
                other_target_columns=other_target_columns,
            ):
                raise ValueError("关系已存在，请勿重复创建")
            if self._same_relation(
                source_table=source_table,
                source_columns=source_columns,
                target_table=target_table,
                target_columns=target_columns,
                other_source_table=item.target_table,
                other_source_columns=other_target_columns,
                other_target_table=item.source_table,
                other_target_columns=other_source_columns,
            ):
                raise ValueError("关系已存在（反向重复），请勿重复创建")

    def _find_duplicate_relation(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        source_table: str,
        source_columns: list[str],
        target_table: str,
        target_columns: list[str],
    ):
        resolved_user_id = self._resolve_user_id(user_id)
        connection_key = self._normalize_connection_key(self._get_connection_key(db, resolved_user_id))
        repo = Text2SQLTableRelationRepository(db)
        existing = repo.list_by_pair(
            user_id=resolved_user_id,
            connection_key=connection_key,
            source_table=source_table,
            target_table=target_table,
        )
        for item in existing:
            other_source_columns = self._safe_load_columns(item.source_columns)
            other_target_columns = self._safe_load_columns(item.target_columns)
            if self._same_relation(
                source_table=source_table,
                source_columns=source_columns,
                target_table=target_table,
                target_columns=target_columns,
                other_source_table=item.source_table,
                other_source_columns=other_source_columns,
                other_target_table=item.target_table,
                other_target_columns=other_target_columns,
            ):
                return item
            if self._same_relation(
                source_table=source_table,
                source_columns=source_columns,
                target_table=target_table,
                target_columns=target_columns,
                other_source_table=item.target_table,
                other_source_columns=other_target_columns,
                other_target_table=item.source_table,
                other_target_columns=other_source_columns,
            ):
                return item
        return None

    def _build_relation_payload(
        self,
        db: Session,
        request: CreateText2SQLRelationRequest | UpdateText2SQLRelationRequest,
        user_id: int | None = None,
    ) -> dict:
        """把请求组装成落库 payload：校验列等长、对齐真实表/列名、计算列哈希、带上连接键。"""
        resolved_user_id = self._resolve_user_id(user_id)
        if len(request.source_columns) != len(request.target_columns):
            raise ValueError("source_columns 与 target_columns 必须等长")

        source_table, source_columns = self._resolve_columns(db, request.source_table, request.source_columns)
        target_table, target_columns = self._resolve_columns(db, request.target_table, request.target_columns)
        if len(source_columns) != len(target_columns):
            raise ValueError("复合键字段数量必须一致")

        relation_type = str(request.relation_type or "").strip() or "N:1"
        description = str(request.description or "").strip()
        connection_key = self._normalize_connection_key(self._get_connection_key(db, resolved_user_id))
        return {
            "user_id": resolved_user_id,
            "connection_key": connection_key,
            "source_table": source_table,
            "source_columns": json.dumps(source_columns, ensure_ascii=False),
            "source_columns_hash": self._build_columns_hash(source_columns),
            "target_table": target_table,
            "target_columns": json.dumps(target_columns, ensure_ascii=False),
            "target_columns_hash": self._build_columns_hash(target_columns),
            "relation_type": relation_type,
            "description": description,
            "is_active": bool(request.is_active),
        }

    def _to_relation_item(self, relation) -> Text2SQLRelationItem:
        return Text2SQLRelationItem(
            id=int(relation.id),
            source_table=str(relation.source_table or ""),
            source_columns=self._safe_load_columns(relation.source_columns),
            target_table=str(relation.target_table or ""),
            target_columns=self._safe_load_columns(relation.target_columns),
            relation_type=str(relation.relation_type or ""),
            description=str(relation.description or ""),
            is_active=bool(relation.is_active),
            created_at=relation.created_at,
            updated_at=relation.updated_at,
        )

    def _get_owned_relation(self, db: Session, relation_id: int, user_id: int | None = None):
        """按 id 取关系并校验归属：必须属于当前用户且同一连接，否则视为「不存在或无权访问」。"""
        resolved_user_id = self._resolve_user_id(user_id)
        repo = Text2SQLTableRelationRepository(db)
        relation = repo.get_by_id(relation_id)
        if relation is None:
            raise ValueError("关系不存在")
        connection_key = self._normalize_connection_key(self._get_connection_key(db, resolved_user_id))
        if int(relation.user_id) != resolved_user_id or str(relation.connection_key) != connection_key:
            raise ValueError("关系不存在或无权访问")
        return relation

    def list_relations(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
        keyword: str = "",
        table_name: str = "",
    ) -> Text2SQLRelationListResponse:
        """分页查询当前用户当前连接下的关系列表（支持关键字与按表名过滤）。"""
        resolved_user_id = self._resolve_user_id(user_id)
        connection_key = self._normalize_connection_key(self._get_connection_key(db, resolved_user_id))
        rows, total = Text2SQLTableRelationRepository(db).list_by_user_and_connection(
            user_id=resolved_user_id,
            connection_key=connection_key,
            keyword=keyword,
            table_name=table_name,
            page=page,
            page_size=page_size,
        )
        return Text2SQLRelationListResponse(
            items=[self._to_relation_item(item) for item in rows],
            total=total,
            page=max(1, int(page)),
            page_size=max(1, int(page_size)),
        )

    def create_relation(
        self,
        db: Session,
        request: CreateText2SQLRelationRequest,
        user_id: int | None = None,
    ) -> Text2SQLRelationItem:
        """新建一条关系：组装 payload → 去重校验 → 落库。"""
        resolved_user_id = self._resolve_user_id(user_id)
        payload = self._build_relation_payload(db, request, user_id=resolved_user_id)
        source_columns = self._safe_load_columns(payload["source_columns"])
        target_columns = self._safe_load_columns(payload["target_columns"])
        self._ensure_no_duplicate_relation(
            db,
            user_id=resolved_user_id,
            source_table=payload["source_table"],
            source_columns=source_columns,
            target_table=payload["target_table"],
            target_columns=target_columns,
        )
        relation = Text2SQLTableRelationRepository(db).create(payload)
        return self._to_relation_item(relation)

    def batch_import_relations(
        self,
        db: Session,
        request: BatchImportText2SQLRelationsRequest,
        user_id: int | None = None,
    ) -> Text2SQLRelationBatchImportResponse:
        """批量导入关系：逐条处理，统计新增/更新/跳过/失败；单条异常不影响其余条目。

        命中已存在关系时，按 overwrite_existing 决定覆盖更新还是跳过。
        """
        resolved_user_id = self._resolve_user_id(user_id)
        repo = Text2SQLTableRelationRepository(db)

        total = len(request.relations)
        created = 0
        updated = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        for index, item in enumerate(request.relations, start=1):
            try:
                payload = self._build_relation_payload(db, item, user_id=resolved_user_id)
                source_columns = self._safe_load_columns(payload["source_columns"])
                target_columns = self._safe_load_columns(payload["target_columns"])
                existing = self._find_duplicate_relation(
                    db,
                    user_id=resolved_user_id,
                    source_table=payload["source_table"],
                    source_columns=source_columns,
                    target_table=payload["target_table"],
                    target_columns=target_columns,
                )
                if existing is None:
                    repo.create(payload)
                    created += 1
                    continue

                if request.overwrite_existing:
                    repo.update(existing, payload)
                    updated += 1
                else:
                    skipped += 1
            except (ValueError, RuntimeError) as exc:
                failed += 1
                errors.append(f"[{index}] {exc}")

        return Text2SQLRelationBatchImportResponse(
            total=total,
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors,
        )

    def update_relation(
        self,
        db: Session,
        relation_id: int,
        request: UpdateText2SQLRelationRequest,
        user_id: int | None = None,
    ) -> Text2SQLRelationItem:
        """更新一条关系：校验归属 → 组装 payload → 去重（排除自身）→ 落库。"""
        resolved_user_id = self._resolve_user_id(user_id)
        relation = self._get_owned_relation(db, relation_id, user_id=resolved_user_id)
        payload = self._build_relation_payload(db, request, user_id=resolved_user_id)
        source_columns = self._safe_load_columns(payload["source_columns"])
        target_columns = self._safe_load_columns(payload["target_columns"])
        self._ensure_no_duplicate_relation(
            db,
            user_id=resolved_user_id,
            source_table=payload["source_table"],
            source_columns=source_columns,
            target_table=payload["target_table"],
            target_columns=target_columns,
            exclude_id=relation_id,
        )
        updated = Text2SQLTableRelationRepository(db).update(relation, payload)
        return self._to_relation_item(updated)

    def delete_relation(self, db: Session, relation_id: int, user_id: int | None = None) -> None:
        """删除一条关系（先校验归属）。"""
        relation = self._get_owned_relation(db, relation_id, user_id=user_id)
        Text2SQLTableRelationRepository(db).delete(relation)

    def get_table_columns(self, db: Session, table_name: str) -> Text2SQLRelationTableColumnsResponse:
        """返回某表的字段清单（供配置关系时选择 JOIN 字段的下拉数据）。"""
        real_table_name = self._resolve_table_name(db, table_name)
        table_detail = self.schema_service.get_table_detail(db, real_table_name)
        columns = [
            ColumnInfo(
                name=str(column.get("name") or ""),
                type=str(column.get("type") or ""),
                comment=str(column.get("comment") or ""),
            )
            for column in table_detail.get("columns", [])
            if str(column.get("name") or "").strip()
        ]
        return Text2SQLRelationTableColumnsResponse(
            table_name=real_table_name,
            table_comment=str(table_detail.get("table_comment") or ""),
            columns=columns,
        )

    def get_active_relations_by_tables(
        self,
        db: Session,
        table_names: list[str],
        user_id: int | None = None,
    ) -> list[dict]:
        """运行期核心：取给定表集合之间「已启用」的关系，整理成关系提示列表。

        返回的每条提示含源/目标表、JOIN 列对、关系类型、可读 summary，
        直接供表路由（关系图扩展）与 SQL 校验（JOIN 白名单）消费。
        """
        resolved_user_id = self._resolve_user_id(user_id)
        resolved_tables, _ = self.schema_service.validate_selected_tables(db, table_names)
        if not resolved_tables:
            return []
        connection_key = self._normalize_connection_key(self._get_connection_key(db, resolved_user_id))
        rows = Text2SQLTableRelationRepository(db).list_active_by_tables(
            user_id=resolved_user_id,
            connection_key=connection_key,
            table_names=resolved_tables,
        )

        relation_hints: list[dict] = []
        for item in rows:
            source_columns = self._safe_load_columns(item.source_columns)
            target_columns = self._safe_load_columns(item.target_columns)
            if not source_columns or len(source_columns) != len(target_columns):
                continue
            relation_hints.append(
                {
                    "id": int(item.id),
                    "source_table": str(item.source_table or ""),
                    "source_columns": source_columns,
                    "target_table": str(item.target_table or ""),
                    "target_columns": target_columns,
                    "relation_type": str(item.relation_type or ""),
                    "description": str(item.description or ""),
                    "summary": self._format_relation_summary(
                        str(item.source_table or ""),
                        source_columns,
                        str(item.target_table or ""),
                        target_columns,
                    ),
                }
            )
        return relation_hints

    @staticmethod
    def relation_hint_lines(relation_hints: list[dict] | None) -> list[str]:
        """把关系提示渲染成可读文本行（如「a.x = b.y（类型: N:1）」），用于提示词与调试展示。"""
        lines: list[str] = []
        for hint in relation_hints or []:
            source_table = str(hint.get("source_table") or "")
            target_table = str(hint.get("target_table") or "")
            source_columns = [str(item).strip() for item in (hint.get("source_columns") or []) if str(item).strip()]
            target_columns = [str(item).strip() for item in (hint.get("target_columns") or []) if str(item).strip()]
            if not source_table or not target_table or len(source_columns) != len(target_columns) or not source_columns:
                continue

            pairs = [f"{source_table}.{left} = {target_table}.{right}" for left, right in zip(source_columns, target_columns)]
            relation_type = str(hint.get("relation_type") or "").strip()
            description = str(hint.get("description") or "").strip()
            suffix_parts = []
            if relation_type:
                suffix_parts.append(f"类型: {relation_type}")
            if description:
                suffix_parts.append(f"说明: {description}")
            suffix = f"（{'；'.join(suffix_parts)}）" if suffix_parts else ""
            lines.append(f"- {' AND '.join(pairs)}{suffix}")
        return lines
