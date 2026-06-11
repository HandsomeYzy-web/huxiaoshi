"""Text2SQL 多数据库方言支持（MySQL / SQL Server）的集中映射与执行前 SQL 转写。

设计要点：整条「生成 → 校验 → 修复」流水线内部统一使用 **MySQL 方言**（sqlglot read/write
均为 mysql），只在「真正执行那一刻」按目标业务库类型，用 sqlglot 把最终 SQL 转写成对应方言
（例如 LIMIT→TOP、反引号→[方括号]、COUNT→COUNT_BIG）。这样新增数据库类型时，绝大多数代码无需
改动，只要在本模块扩展映射即可。

本模块只负责「类型 ↔ 方言/驱动/默认值」的纯映射与无副作用的 SQL 转写，不持有连接、不读配置。
"""

from __future__ import annotations

import sqlglot

# —— 受支持的业务库类型（前端下拉、保存校验、URI 构造都以此为准）——
DB_TYPE_MYSQL = "mysql"
DB_TYPE_SQLSERVER = "sqlserver"

SUPPORTED_DB_TYPES: tuple[str, ...] = (DB_TYPE_MYSQL, DB_TYPE_SQLSERVER)

# 常见写法 → 规范化 db_type（容错前端/历史数据里的别名）。
_DB_TYPE_ALIASES: dict[str, str] = {
    "mysql": DB_TYPE_MYSQL,
    "mariadb": DB_TYPE_MYSQL,
    "sqlserver": DB_TYPE_SQLSERVER,
    "sql_server": DB_TYPE_SQLSERVER,
    "sql server": DB_TYPE_SQLSERVER,
    "mssql": DB_TYPE_SQLSERVER,
    "ms sql": DB_TYPE_SQLSERVER,
    "microsoft sql server": DB_TYPE_SQLSERVER,
}

# db_type → sqlglot 方言名（流水线内部恒为 mysql，仅执行时转写到目标方言）。
_SQLGLOT_DIALECT: dict[str, str] = {
    DB_TYPE_MYSQL: "mysql",
    DB_TYPE_SQLSERVER: "tsql",
}

# db_type → SQLAlchemy 驱动 scheme。
_SQLALCHEMY_DRIVER: dict[str, str] = {
    DB_TYPE_MYSQL: "mysql+pymysql",
    DB_TYPE_SQLSERVER: "mssql+pymssql",
}

# db_type → 默认端口。
_DEFAULT_PORT: dict[str, int] = {
    DB_TYPE_MYSQL: 3306,
    DB_TYPE_SQLSERVER: 1433,
}

# db_type → 默认字符集。
_DEFAULT_CHARSET: dict[str, str] = {
    DB_TYPE_MYSQL: "utf8mb4",
    DB_TYPE_SQLSERVER: "UTF-8",
}


def normalize_db_type(db_type: str | None) -> str:
    """把任意大小写/别名的库类型规范化为标准 db_type；未知值原样小写返回。"""
    key = str(db_type or "").strip().lower()
    return _DB_TYPE_ALIASES.get(key, key)


def is_supported_db_type(db_type: str | None) -> bool:
    """该库类型是否在受支持列表内。"""
    return normalize_db_type(db_type) in SUPPORTED_DB_TYPES


def sqlglot_dialect_for(db_type: str | None) -> str:
    """返回该库类型对应的 sqlglot 方言名（未知类型回退 mysql）。"""
    return _SQLGLOT_DIALECT.get(normalize_db_type(db_type), "mysql")


def sqlalchemy_driver_for(db_type: str | None) -> str:
    """返回该库类型对应的 SQLAlchemy 驱动 scheme（未知类型回退 MySQL 驱动）。"""
    return _SQLALCHEMY_DRIVER.get(normalize_db_type(db_type), _SQLALCHEMY_DRIVER[DB_TYPE_MYSQL])


def default_port_for(db_type: str | None) -> int:
    """返回该库类型的默认端口（未知类型回退 3306）。"""
    return _DEFAULT_PORT.get(normalize_db_type(db_type), 3306)


def default_charset_for(db_type: str | None) -> str:
    """返回该库类型的默认字符集（未知类型回退 utf8mb4）。"""
    return _DEFAULT_CHARSET.get(normalize_db_type(db_type), "utf8mb4")


def transpile_for_execution(sql: str, db_type: str | None) -> str:
    """把流水线产出的 MySQL 方言 SQL 转写为目标库方言，供执行使用。

    - 目标即 MySQL 时原样返回（零成本）；
    - 转写失败时安全回退原 SQL（让数据库自身报错，便于定位），不抛异常。
    """
    target = sqlglot_dialect_for(db_type)
    sql_text = str(sql or "").strip().rstrip(";")
    if not sql_text or target == "mysql":
        return sql
    try:
        transpiled = sqlglot.transpile(sql_text, read="mysql", write=target)
    except Exception:  # noqa: BLE001
        return sql
    if not transpiled:
        return sql
    return transpiled[0]
