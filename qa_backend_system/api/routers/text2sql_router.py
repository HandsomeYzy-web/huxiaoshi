"""Text2SQL 路由聚合入口。

统一挂载 /text2sql 前缀，并把各子路由（连接管理、表/字段权限、关系白名单、查询）汇总成一个
APIRouter 供 main 注册。各子路由的具体业务接口见对应 *_router 文件。
"""

from fastapi import APIRouter

from . import (
    text2sql_connection_router,
    text2sql_query_router,
    text2sql_relation_router,
    text2sql_table_router,
)

router = APIRouter(prefix="/text2sql", tags=["Text2SQL"])

# 按「连接 → 表/字段权限 → 关系 → 查询」的使用顺序挂载子路由。

router.include_router(text2sql_connection_router.router)
router.include_router(text2sql_table_router.router)
router.include_router(text2sql_relation_router.router)
router.include_router(text2sql_query_router.router)
