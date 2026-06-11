"""text2sql_config 表的数据访问层（旧版「按用户」全局配置，保留兼容）。

新逻辑改用 text2sql_scoped_config（按用户+连接隔离），本仓储仅在 scoped 配置缺失时回退读取。
查询统一过滤软删除标记 is_deleted。
"""

from sqlalchemy.orm import Session

from models.entities.text2sql_config import Text2SQLConfig

class Text2SQLConfigRepository:
    """负责 `text2sql_config` 表的读写。"""
    def __init__(self, db: Session):
        """注入数据库会话。"""
        self.db = db

    def get_by_user_id(self, user_id: int) -> Text2SQLConfig | None:
        """按用户 ID 读取配置记录。"""
        return (
            self.db.query(Text2SQLConfig)
            .filter(
                Text2SQLConfig.user_id == user_id,
                Text2SQLConfig.is_deleted == False,  # noqa: E712
            )
            .first()
        )

    def upsert(
        self,
        user_id: int,
        selected_tables: str | None,
        prompt_hint: str | None,
    ) -> Text2SQLConfig:
        """按用户维度创建或更新配置记录。"""
        config = self.get_by_user_id(user_id)
        if config is None:
            config = Text2SQLConfig(
                user_id=user_id,
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

