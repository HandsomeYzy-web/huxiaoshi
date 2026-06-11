"""text2sql_field_permission 表的数据访问层（字段级查询开关的持久化）。

按「用户 + 连接」读取权限记录，并以「整表覆盖」的方式重写某张表的字段开关。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.entities.text2sql_field_permission import Text2SQLFieldPermission


class Text2SQLFieldPermissionRepository:
    """text2sql_field_permission 表的增删改查。"""

    def __init__(self, db: Session):
        """注入数据库会话。"""
        self.db = db

    def list_by_user_and_connection(
        self,
        user_id: int,
        connection_key: str,
        table_name: str | None = None,
    ) -> list[Text2SQLFieldPermission]:
        """按「用户 + 连接」（可选再按表名）列出字段权限记录。"""
        query = self.db.query(Text2SQLFieldPermission).filter(
            Text2SQLFieldPermission.user_id == user_id,
            Text2SQLFieldPermission.connection_key == connection_key,
        )
        if table_name:
            query = query.filter(Text2SQLFieldPermission.table_name == table_name)
        return query.all()

    def replace_table_permissions(
        self,
        *,
        user_id: int,
        connection_key: str,
        table_name: str,
        permissions: dict[str, bool],
    ) -> list[Text2SQLFieldPermission]:
        """整表覆盖：先删除该表旧的字段权限记录，再按 permissions 全量重建（保证状态一致）。"""
        (
            self.db.query(Text2SQLFieldPermission)
            .filter(
                Text2SQLFieldPermission.user_id == user_id,
                Text2SQLFieldPermission.connection_key == connection_key,
                Text2SQLFieldPermission.table_name == table_name,
            )
            .delete(synchronize_session=False)
        )
        records: list[Text2SQLFieldPermission] = []
        for column_name, query_enabled in permissions.items():
            record = Text2SQLFieldPermission(
                user_id=user_id,
                connection_key=connection_key,
                table_name=table_name,
                column_name=column_name,
                query_enabled=bool(query_enabled),
            )
            self.db.add(record)
            records.append(record)

        self.db.commit()
        for record in records:
            self.db.refresh(record)
        return records
