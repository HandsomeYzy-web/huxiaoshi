"""Text2SQL 目标业务库「连接管理」服务。

负责被查询的业务库连接配置的保存、连通性测试与运行时引擎缓存：
- 密码落库前用 ConnectionPasswordCipher 加密，对外接口（get_public_connection）从不返回明文密码；
- 保存/测试时若密码留空且目标与已存连接一致，则复用已保存的密码，避免前端反复回填；
- 运行时引擎按 URI 缓存并复用（连接变更后失效重建），避免每次查询都新建连接池。
注意区分本系统自身的库与「被查询的业务库」——本服务管理的是后者。
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session

from core.connection_password_cipher import ConnectionPasswordCipher
from models.schemas.text2sql_schema import Text2SQLConnectionPayload, Text2SQLConnectionResponse
from repositories.text2sql_connection_repo import Text2SQLConnectionRepository
from services.text2sql.sql_dialect import (
    DB_TYPE_MYSQL,
    DB_TYPE_SQLSERVER,
    SUPPORTED_DB_TYPES,
    default_charset_for,
    default_port_for,
    is_supported_db_type,
    normalize_db_type,
    sqlalchemy_driver_for,
)


class Text2SQLConnectionService:
    """管理数据库连接配置、连通性测试和运行时引擎缓存。"""

    def __init__(self):
        self._cached_engine: Engine | None = None
        self._cached_uri: str = ""
        self._password_cipher = ConnectionPasswordCipher()

    @staticmethod
    def _build_uri(
        *,
        db_type: str,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        charset: str,
    ) -> str:
        """按库类型构造 SQLAlchemy 连接 URI，自动处理用户名/密码特殊字符。

        MySQL 走 mysql+pymysql，SQL Server 走 mssql+pymssql；charset 留空时按库类型取默认值。
        """
        normalized_db_type = normalize_db_type(db_type)
        resolved_charset = str(charset or "").strip() or default_charset_for(normalized_db_type)
        url = URL.create(
            sqlalchemy_driver_for(normalized_db_type),
            username=username,
            password=password,
            host=host,
            port=int(port),
            database=database,
            query={"charset": resolved_charset},
        )
        # `str(url)` masks password as "***", which breaks runtime authentication.
        return url.render_as_string(hide_password=False)

    @staticmethod
    def _strip(value: str | None, fallback: str = "") -> str:
        if value is None:
            return fallback
        return str(value).strip()

    def get_public_connection(self, db: Session) -> Text2SQLConnectionResponse:
        """返回「脱敏」的当前连接信息：只暴露是否配置了密码（has_password），不返回密码本身。"""
        record = Text2SQLConnectionRepository(db).get_active()
        if record is None:
            return Text2SQLConnectionResponse(configured=False)
        return Text2SQLConnectionResponse(
            configured=True,
            db_type=normalize_db_type(record.db_type),
            host=record.host,
            port=record.port,
            username=record.username,
            database=record.database,
            charset=record.charset,
            has_password=bool(record.password),
        )

    def get_active_db_type(self, db: Session) -> str:
        """返回当前生效连接的规范化库类型（未配置时回退 mysql）。

        供执行器/枚举探测在「执行 SQL 前」据此把 SQL 转写到目标方言、并切换会话级语句。
        """
        record = Text2SQLConnectionRepository(db).get_active()
        if record is None:
            return DB_TYPE_MYSQL
        return normalize_db_type(record.db_type)

    def _test_uri(self, uri: str) -> None:
        """用一条 SELECT 1 探活连接，验证 URI 是否可连通；用完即释放临时引擎。"""
        engine = create_engine(uri, pool_pre_ping=True, pool_recycle=3600, echo=False)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()

    def _is_same_target(
        self,
        *,
        host: str | None,
        port: int | None,
        username: str | None,
        database: str | None,
        payload: Text2SQLConnectionPayload,
    ) -> bool:
        """判断本次提交的连接目标（主机/端口/用户/库）是否与已保存连接完全一致。"""
        default_port = default_port_for(payload.db_type)
        payload_host = self._strip(payload.host).lower()
        payload_port = int(payload.port or default_port)
        payload_username = self._strip(payload.username).lower()
        payload_database = self._strip(payload.database).lower()
        return (
            self._strip(host).lower() == payload_host
            and int(port or default_port) == payload_port
            and self._strip(username).lower() == payload_username
            and self._strip(database).lower() == payload_database
        )

    def _resolve_reusable_password(
        self,
        db: Session,
        payload: Text2SQLConnectionPayload,
        *,
        empty_password_error: str,
    ) -> str:
        """密码留空时的复用逻辑：仅当目标与已存连接一致才解密复用旧密码，否则报错要求重新输入。"""
        current = Text2SQLConnectionRepository(db).get_active()
        if (
            current is not None
            and self._strip(current.password)
            and self._is_same_target(
                host=current.host,
                port=current.port,
                username=current.username,
                database=current.database,
                payload=payload,
            )
        ):
            return self._strip(self._password_cipher.decrypt(current.password))
        raise ValueError(empty_password_error)

    def test_connection(self, db: Session, payload: Text2SQLConnectionPayload) -> None:
        """测试连接：拼出 URI 并探活，不落库（仅校验目标库是否可连）。"""
        password = self._strip(payload.password)
        if not password:
            password = self._resolve_reusable_password(
                db,
                payload,
                empty_password_error="测试连接时 password 不能为空（仅当目标与已保存连接一致时可留空）",
            )

        uri = self._build_uri(
            db_type=payload.db_type,
            host=self._strip(payload.host),
            port=payload.port,
            username=self._strip(payload.username),
            password=password,
            database=self._strip(payload.database),
            charset=self._strip(payload.charset),
        )
        self._test_uri(uri)

    def save_connection(self, db: Session, payload: Text2SQLConnectionPayload) -> Text2SQLConnectionResponse:
        """保存连接：先探活确认可连通，密码加密后落库，并失效旧引擎缓存以便下次重建。"""
        normalized_db_type = normalize_db_type(payload.db_type)
        if not is_supported_db_type(normalized_db_type):
            raise ValueError(f"不支持的数据库类型: {payload.db_type}（当前支持: {', '.join(SUPPORTED_DB_TYPES)}）")

        password = self._strip(payload.password)
        if not password:
            password = self._resolve_reusable_password(
                db,
                payload,
                empty_password_error="保存连接时 password 不能为空（修改目标后请重新输入密码）",
            )

        uri = self._build_uri(
            db_type=normalized_db_type,
            host=self._strip(payload.host),
            port=payload.port,
            username=self._strip(payload.username),
            password=password,
            database=self._strip(payload.database),
            charset=self._strip(payload.charset),
        )
        self._test_uri(uri)

        encrypted_password = self._password_cipher.encrypt(password)
        Text2SQLConnectionRepository(db).upsert(
            db_type=normalized_db_type,
            host=self._strip(payload.host),
            port=payload.port,
            username=self._strip(payload.username),
            password=encrypted_password,
            database=self._strip(payload.database),
            charset=self._strip(payload.charset) or default_charset_for(normalized_db_type),
        )

        self._reset_engine_cache()
        return self.get_public_connection(db)

    def _resolve_runtime_uri(self, db: Session) -> str:
        """读取当前生效连接并解密密码，拼出运行时可用的完整 URI（未配置时返回空串）。"""
        record = Text2SQLConnectionRepository(db).get_active()
        if record is None:
            return ""
        decrypted_password = self._password_cipher.decrypt(record.password)
        return self._build_uri(
            db_type=record.db_type,
            host=record.host,
            port=record.port,
            username=record.username,
            password=decrypted_password,
            database=record.database,
            charset=record.charset,
        )

    def get_engine(self, db: Session) -> Engine:
        """获取业务库运行时引擎：按 URI 缓存复用，连接变更（URI 不同）时释放旧引擎并重建。"""
        uri = self._resolve_runtime_uri(db)
        if not uri:
            raise RuntimeError("数据库连接未配置，请先保存数据库连接")

        if self._cached_engine is None or self._cached_uri != uri:
            if self._cached_engine is not None:
                self._cached_engine.dispose()
            self._cached_engine = create_engine(uri, pool_pre_ping=True, pool_recycle=3600, echo=False)
            self._cached_uri = uri
        return self._cached_engine

    def _reset_engine_cache(self) -> None:
        """失效引擎缓存：释放已有连接池并清空缓存（连接配置变更后调用）。"""
        if self._cached_engine is not None:
            self._cached_engine.dispose()
        self._cached_engine = None
        self._cached_uri = ""
