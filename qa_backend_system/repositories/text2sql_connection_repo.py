"""text2sql_connection 表的数据访问层（业务库连接配置的持久化）。

仅做单表读写，不涉及加解密与连通性校验（那些在 connection_service）。系统约定「当前生效连接」
为最近更新的一条记录，upsert 即在其上覆盖更新、不存在则新建。
"""

from sqlalchemy import desc
from sqlalchemy.orm import Session

from models.entities.text2sql_connection import Text2SQLConnection

class Text2SQLConnectionRepository:
    """负责 `text2sql_connection` 表的读写。"""
    def __init__(self, db: Session):
        """注入数据库会话。"""
        self.db = db

    def get_active(self) -> Text2SQLConnection | None:
        """返回最近一次保存的连接配置。"""
        return self.db.query(Text2SQLConnection).order_by(desc(Text2SQLConnection.updated_at)).first()

    def upsert(
        self,
        *,
        db_type: str,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        charset: str,
    ) -> Text2SQLConnection:
        """创建或更新当前生效的连接配置。"""
        record = self.get_active()
        if record is None:
            record = Text2SQLConnection(
                db_type=db_type,
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                charset=charset,
            )
            self.db.add(record)
        else:
            record.db_type = db_type
            record.host = host
            record.port = port
            record.username = username
            record.password = password
            record.database = database
            record.charset = charset
        self.db.commit()
        self.db.refresh(record)
        return record

