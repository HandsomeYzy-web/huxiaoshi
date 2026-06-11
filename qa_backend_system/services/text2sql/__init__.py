"""Text2SQL 服务包：装配各子服务单例并对外暴露。

本文件是整个 Text2SQL 模块的「依赖装配中心」：按依赖关系顺序构建各服务的共享单例，
并组装出总编排器 facade_service。各路由层统一从这里导入 *_service 单例，避免重复实例化。

依赖关系（自底向上）：
    connection_service（连接/引擎）
      └─ schema_service（表结构元数据）
           ├─ config_service（用户选表与 prompt）
           ├─ field_permission_service（表/字段权限）
           └─ relation_service（JOIN 关系白名单）
    log_service（查询日志）
    facade_service（总编排，注入以上全部）
"""

from services.text2sql.config_service import Text2SQLConfigService
from services.text2sql.connection_service import Text2SQLConnectionService
from services.text2sql.facade_service import Text2SQLFacadeService
from services.text2sql.field_permission_service import Text2SQLFieldPermissionService
from services.text2sql.log_service import Text2SQLLogService
from services.text2sql.relation_service import Text2SQLRelationService
from services.text2sql.schema_service import Text2SQLSchemaService

connection_service = Text2SQLConnectionService()
schema_service = Text2SQLSchemaService(connection_service)
config_service = Text2SQLConfigService(schema_service, connection_service)
field_permission_service = Text2SQLFieldPermissionService(schema_service, config_service)
relation_service = Text2SQLRelationService(schema_service, config_service)
log_service = Text2SQLLogService()
facade_service = Text2SQLFacadeService(
    connection_service=connection_service,
    schema_service=schema_service,
    config_service=config_service,
    field_permission_service=field_permission_service,
    relation_service=relation_service,
    log_service=log_service,
)

__all__ = [
    "connection_service",
    "schema_service",
    "config_service",
    "field_permission_service",
    "relation_service",
    "log_service",
    "facade_service",
    "Text2SQLConnectionService",
    "Text2SQLSchemaService",
    "Text2SQLConfigService",
    "Text2SQLFieldPermissionService",
    "Text2SQLRelationService",
    "Text2SQLLogService",
    "Text2SQLFacadeService",
]
