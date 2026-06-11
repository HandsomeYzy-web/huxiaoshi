"""text2sql_table_relation 表的数据访问层（JOIN 关系白名单的持久化）。

提供分页/关键字/表名过滤的列表查询、增删改、按表对查重复（含反向），以及运行期最关键的
list_active_by_tables——取「两端表都在给定集合内、且已启用」的关系，供路由与校验消费。
"""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.entities.text2sql_table_relation import Text2SQLTableRelation


class Text2SQLTableRelationRepository:
    """text2sql_table_relation 表的增删改查。"""

    def __init__(self, db: Session):
        """注入数据库会话。"""
        self.db = db

    def list_by_user_and_connection(
        self,
        *,
        user_id: int,
        connection_key: str,
        keyword: str | None = None,
        table_name: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Text2SQLTableRelation], int]:
        """分页查询关系列表，返回（当前页记录, 总数）。

        keyword 模糊匹配源/目标表名与描述；table_name 精确匹配源或目标表；按更新时间倒序。
        """
        query = self.db.query(Text2SQLTableRelation).filter(
            Text2SQLTableRelation.user_id == user_id,
            Text2SQLTableRelation.connection_key == connection_key,
        )
        safe_keyword = str(keyword or "").strip().lower()
        if safe_keyword:
            pattern = f"%{safe_keyword}%"
            query = query.filter(
                or_(
                    Text2SQLTableRelation.source_table.ilike(pattern),
                    Text2SQLTableRelation.target_table.ilike(pattern),
                    Text2SQLTableRelation.description.ilike(pattern),
                )
            )

        safe_table_name = str(table_name or "").strip()
        if safe_table_name:
            query = query.filter(
                or_(
                    Text2SQLTableRelation.source_table == safe_table_name,
                    Text2SQLTableRelation.target_table == safe_table_name,
                )
            )

        total = int(query.count())
        safe_page = max(1, int(page))
        safe_page_size = max(1, int(page_size))
        rows = (
            query.order_by(
                Text2SQLTableRelation.updated_at.desc(),
                Text2SQLTableRelation.id.desc(),
            )
            .offset((safe_page - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        return rows, total

    def get_by_id(self, relation_id: int) -> Text2SQLTableRelation | None:
        """按主键获取关系（归属校验由服务层负责）。"""
        return self.db.query(Text2SQLTableRelation).filter(Text2SQLTableRelation.id == relation_id).first()

    def create(self, payload: dict) -> Text2SQLTableRelation:
        """按 payload 新建一条关系记录。"""
        relation = Text2SQLTableRelation(**payload)
        self.db.add(relation)
        self.db.commit()
        self.db.refresh(relation)
        return relation

    def update(self, relation: Text2SQLTableRelation, payload: dict) -> Text2SQLTableRelation:
        """用 payload 覆盖更新已有关系记录的字段。"""
        for key, value in payload.items():
            setattr(relation, key, value)
        self.db.commit()
        self.db.refresh(relation)
        return relation

    def delete(self, relation: Text2SQLTableRelation) -> None:
        """删除一条关系记录。"""
        self.db.delete(relation)
        self.db.commit()

    def list_active_by_tables(
        self,
        *,
        user_id: int,
        connection_key: str,
        table_names: list[str],
    ) -> list[Text2SQLTableRelation]:
        """运行期核心：取源表与目标表「都落在 table_names 内、且已启用」的关系。"""
        if not table_names:
            return []
        return (
            self.db.query(Text2SQLTableRelation)
            .filter(
                Text2SQLTableRelation.user_id == user_id,
                Text2SQLTableRelation.connection_key == connection_key,
                Text2SQLTableRelation.is_active == True,  # noqa: E712
                Text2SQLTableRelation.source_table.in_(table_names),
                Text2SQLTableRelation.target_table.in_(table_names),
            )
            .all()
        )

    def list_by_pair(
        self,
        *,
        user_id: int,
        connection_key: str,
        source_table: str,
        target_table: str,
        exclude_id: int | None = None,
    ) -> list[Text2SQLTableRelation]:
        """取某「表对」之间的所有关系（正向 + 反向），供服务层判重；exclude_id 用于更新时排除自身。"""
        query = self.db.query(Text2SQLTableRelation).filter(
            Text2SQLTableRelation.user_id == user_id,
            Text2SQLTableRelation.connection_key == connection_key,
            or_(
                (
                    (Text2SQLTableRelation.source_table == source_table)
                    & (Text2SQLTableRelation.target_table == target_table)
                ),
                (
                    (Text2SQLTableRelation.source_table == target_table)
                    & (Text2SQLTableRelation.target_table == source_table)
                ),
            ),
        )
        if exclude_id is not None:
            query = query.filter(Text2SQLTableRelation.id != int(exclude_id))
        return query.all()
