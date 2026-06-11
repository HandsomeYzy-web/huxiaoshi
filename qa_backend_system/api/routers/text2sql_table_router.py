"""Text2SQL 表结构与表/字段权限配置路由。

汇集与「表」相关的管理接口：查看实时表结构、列出可选表、读写用户选表配置（哪些表参与查询）、
以及表内字段级查询开关的读写。选表与字段开关按当前用户隔离（用户身份由统一认证平台经请求头注入）。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_id
from core.database import get_db
from core.exceptions import BusinessError
from core.response import UnifiedResponse, success
from models.schemas.text2sql_schema import (
    Text2SQLConfigResponse,
    Text2SQLSchemaResponse,
    Text2SQLTableFieldsResponse,
    Text2SQLTableOptionsResponse,
    UpdateText2SQLConfigRequest,
    UpdateText2SQLTableFieldsRequest,
)
from services.text2sql import config_service, facade_service, field_permission_service

router = APIRouter(tags=["Text2SQL"])


@router.get(
    "/tables/schema",
    response_model=UnifiedResponse[Text2SQLSchemaResponse],
)
async def get_table_schema(
    table_names: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """查看实时表结构（不传 table_names 则返回全部表）。"""
    try:
        data = facade_service.list_schema_overview(db, table_names)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Fetched table schema")


@router.get(
    "/tables/options",
    response_model=UnifiedResponse[Text2SQLTableOptionsResponse],
)
async def get_table_options(db: Session = Depends(get_db)):
    """列出连接下全部可配置的表（供前端选表 / 配权限）。"""
    try:
        data = field_permission_service.get_table_options(db)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Fetched table options")


@router.get(
    "/tables/config",
    response_model=UnifiedResponse[Text2SQLConfigResponse],
)
async def get_table_config(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """读取当前用户在当前连接下的选表与 prompt 配置。"""
    try:
        data = config_service.get_config(db, user_id=user_id)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Fetched Text2SQL config")


@router.put(
    "/tables/config",
    response_model=UnifiedResponse[Text2SQLConfigResponse],
)
async def update_table_config(
    request: UpdateText2SQLConfigRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """更新当前用户的选表与 prompt 配置（会校验所选表是否存在）。"""
    try:
        data = config_service.update_config(db, request, user_id=user_id)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Updated Text2SQL config")


@router.get(
    "/tables/{table_name}/fields",
    response_model=UnifiedResponse[Text2SQLTableFieldsResponse],
)
async def get_table_fields(
    table_name: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """读取某表各字段的查询开关状态（未配置的字段默认可查）。"""
    try:
        data = field_permission_service.get_table_fields(db, table_name, user_id=user_id)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Fetched field permissions")


@router.put(
    "/tables/{table_name}/fields",
    response_model=UnifiedResponse[Text2SQLTableFieldsResponse],
)
async def update_table_fields(
    table_name: str,
    request: UpdateText2SQLTableFieldsRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """更新某表的字段查询开关（至少需保留一个可查字段）。"""
    try:
        data = field_permission_service.update_table_fields(
            db,
            table_name,
            request,
            user_id=user_id,
        )
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Updated field permissions")
