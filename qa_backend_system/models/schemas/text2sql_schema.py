"""Text2SQL 接口请求/响应数据模型（Pydantic Schema）。

定义对外 API 的入参与出参契约，覆盖连接配置、表/字段结构与权限、表关系、问答查询、
调试生成、查询日志等。约定：响应模型一律不含明文密码；带 from_attributes 的模型可直接由
ORM 实体转换。这里只做数据形状与字段校验（长度/范围/枚举），业务逻辑在 services 层。
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Text2SQLConnectionPayload(BaseModel):
    """前端提交的数据库连接参数（支持 MySQL / SQL Server）。"""

    db_type: Literal["mysql", "sqlserver"] = "mysql"
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=3306, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=255)
    password: str | None = Field(default=None, max_length=255)
    database: str = Field(min_length=1, max_length=255)
    charset: str = Field(default="utf8mb4", min_length=1, max_length=64)


class Text2SQLConnectionResponse(BaseModel):
    """返回给前端的连接配置（不包含明文密码）。"""

    configured: bool = False
    db_type: Literal["mysql", "sqlserver"] | None = None
    host: str = ""
    port: int = 3306
    username: str = ""
    database: str = ""
    charset: str = "utf8mb4"
    has_password: bool = False


class Text2SQLConnectionTestResponse(BaseModel):
    """连接测试接口的返回结构。"""

    ok: bool
    message: str = ""


class ColumnInfo(BaseModel):
    """单个字段的基础信息。"""

    name: str
    type: str
    comment: str = ""


class TableInfo(BaseModel):
    """单张表的结构信息。"""

    table_name: str
    table_comment: str = ""
    columns: list[ColumnInfo] = Field(default_factory=list)


class Text2SQLSchemaResponse(BaseModel):
    """数据库 Schema 概览响应。"""

    tables: list[TableInfo] = Field(default_factory=list)


class Text2SQLTableOption(BaseModel):
    """表开关页面展示的表项。"""

    table_name: str
    table_comment: str = ""


class Text2SQLTableOptionsResponse(BaseModel):
    """表开关页面的表列表响应。"""

    tables: list[Text2SQLTableOption] = Field(default_factory=list)


class Text2SQLTableFieldItem(BaseModel):
    """字段开关页面的单个字段项。"""

    name: str
    type: str
    comment: str = ""
    query_enabled: bool = True


class Text2SQLTableFieldsResponse(BaseModel):
    """字段开关页面的整表字段响应。"""

    table_name: str
    table_comment: str = ""
    fields: list[Text2SQLTableFieldItem] = Field(default_factory=list)


class Text2SQLConfigResponse(BaseModel):
    """当前连接对应的配置响应。"""

    selected_tables: list[str] = Field(default_factory=list)
    prompt_hint: str = ""


class UpdateText2SQLConfigRequest(BaseModel):
    """更新表开关和提示词时的请求体。"""

    selected_tables: list[str] = Field(default_factory=list)
    prompt_hint: str = ""


class UpdateText2SQLTableFieldItem(BaseModel):
    """更新单个字段开关的请求项。"""

    name: str = Field(min_length=1, max_length=255)
    query_enabled: bool = True


class UpdateText2SQLTableFieldsRequest(BaseModel):
    """更新整张表字段开关的请求体。"""

    fields: list[UpdateText2SQLTableFieldItem] = Field(default_factory=list, min_length=1)


class Text2SQLRelationUpsertRequest(BaseModel):
    """新增/更新表关系的请求体（支持复合键）。"""

    source_table: str = Field(min_length=1, max_length=64)
    source_columns: list[str] = Field(default_factory=list, min_length=1)
    target_table: str = Field(min_length=1, max_length=64)
    target_columns: list[str] = Field(default_factory=list, min_length=1)
    relation_type: str = Field(default="N:1", max_length=16)
    description: str = ""
    is_active: bool = True


class CreateText2SQLRelationRequest(Text2SQLRelationUpsertRequest):
    """新增关系请求。"""


class UpdateText2SQLRelationRequest(Text2SQLRelationUpsertRequest):
    """更新关系请求。"""


class BatchImportText2SQLRelationsRequest(BaseModel):
    """批量导入关系请求（overwrite_existing 控制命中已有关系时覆盖还是跳过）。"""

    relations: list[CreateText2SQLRelationRequest] = Field(default_factory=list, min_length=1)
    overwrite_existing: bool = False


class Text2SQLRelationItem(BaseModel):
    """关系配置条目。"""

    id: int
    source_table: str
    source_columns: list[str] = Field(default_factory=list)
    target_table: str
    target_columns: list[str] = Field(default_factory=list)
    relation_type: str = ""
    description: str = ""
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Text2SQLRelationListResponse(BaseModel):
    """关系列表分页响应。"""

    items: list[Text2SQLRelationItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class Text2SQLRelationBatchImportResponse(BaseModel):
    """批量导入结果统计（总数 / 新增 / 更新 / 跳过 / 失败 + 错误明细）。"""

    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)


class Text2SQLRelationTableColumnsResponse(BaseModel):
    """关系配置时读取表字段列表的响应。"""

    table_name: str
    table_comment: str = ""
    columns: list[ColumnInfo] = Field(default_factory=list)


class Text2SQLTurn(BaseModel):
    """多轮对话中的单轮历史（前端持有并随每次请求回传）。"""

    question: str = Field(default="", max_length=4000)
    sql: str = Field(default="", max_length=8000)
    answer: str = Field(default="", max_length=4000)


class Text2SQLQueryRequest(BaseModel):
    """自然语言问答请求体。"""

    question: str = Field(min_length=1, max_length=4000)
    history: list[Text2SQLTurn] = Field(default_factory=list, max_length=20)


class Text2SQLFieldInferenceItem(BaseModel):
    """查询结果字段与数据库注释的绑定信息。"""

    column: str
    inferred_meaning: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""
    table_name: str = ""
    table_comment: str = ""
    column_name: str = ""
    column_comment: str = ""


class Text2SQLQueryResponse(BaseModel):
    """问答接口返回的 SQL、数据和总结。"""

    sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    answer: str
    row_count: int = 0
    repaired: bool = False
    field_inference: list[Text2SQLFieldInferenceItem] = Field(default_factory=list)
    # 本次查询对应的日志 id；前端凭此提交满意度评分（用于 few-shot 示例晋升）。
    log_id: int | None = None
    # 非空时表示路由信号不足、需要用户补充澄清；此时不会生成/执行 SQL。
    clarification: str = ""


class Text2SQLFeedbackRequest(BaseModel):
    """用户对某条查询结果的满意度评分请求（1-5 星）。"""

    log_id: int = Field(ge=1)
    score: int = Field(ge=1, le=5)


class Text2SQLDebugGenerateResponse(BaseModel):
    """调试接口返回的 SQL 生成与校验信息。"""

    sql: str
    validation_passed: bool
    validation_message: str = ""
    route_mode: str = ""
    route_tables: list[str] = Field(default_factory=list)
    route_pool_tables: list[str] = Field(default_factory=list)
    route_scores: dict[str, float] = Field(default_factory=dict)
    relation_hints: list[str] = Field(default_factory=list)
    relation_guard_used: bool = False


class Text2SQLQueryLogItem(BaseModel):
    """查询日志列表中的单条记录。"""

    id: int
    question: str
    generated_sql: str | None = None
    final_sql: str | None = None
    status: str
    error_message: str | None = None
    relation_guard_used: bool = False
    row_count: int | None = None
    duration_ms: int | None = None
    repaired: bool
    feedback_score: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
