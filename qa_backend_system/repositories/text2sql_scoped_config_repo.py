"""text2sql_scoped_config 表的数据访问层（当前主用配置，按用户+连接隔离）。

按 (user_id, connection_key) 读写用户在某连接下的选表与 prompt 配置，查询过滤软删除标记。
"""

from sqlalchemy.orm import Session

from models.entities.text2sql_scoped_config import Text2SQLScopedConfig


class Text2SQLScopedConfigRepository:
    """text2sql_scoped_config 表的增删改查。"""

    def __init__(self, db: Session):
        """注入数据库会话。"""
        self.db = db

    def get_by_user_and_connection(self, user_id: int, connection_key: str) -> Text2SQLScopedConfig | None:
        """按「用户 + 连接」读取未删除的配置记录。"""
        return (
            self.db.query(Text2SQLScopedConfig)
            .filter(
                Text2SQLScopedConfig.user_id == user_id,
                Text2SQLScopedConfig.connection_key == connection_key,
                Text2SQLScopedConfig.is_deleted == False,  # noqa: E712
            )
            .first()
        )

    def upsert(
        self,
        *,
        user_id: int,
        connection_key: str,
        selected_tables: str | None,
        prompt_hint: str | None,
    ) -> Text2SQLScopedConfig:
        """按「用户 + 连接」创建或更新配置（命中则覆盖，并复活软删除记录）。"""
        config = self.get_by_user_and_connection(user_id, connection_key)
        if config is None:
            config = Text2SQLScopedConfig(
                user_id=user_id,
                connection_key=connection_key,
                selected_tables=selected_tables,
                prompt_hint=prompt_hint,
                is_deleted=False,
            )
            self.db.add(config)
        else:
            config.selected_tables = selected_tables
            config.prompt_hint = prompt_hint
            config.is_deleted = False
        self.db.commit()
        self.db.refresh(config)
        return config
