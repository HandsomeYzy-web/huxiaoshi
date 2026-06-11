"""Text2SQL 表关系（JOIN 白名单）管理路由。

提供关系的增删改查、批量导入，以及配置关系时所需的表字段查询接口。这里登记的关系即多表查询的
JOIN 白名单——只有登记过的关系才允许模型 JOIN。写操作按当前用户隔离（用户身份由统一认证平台经请求头注入）。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_id
from core.database import get_db
from core.exceptions import BusinessError
from core.response import UnifiedResponse, success
from models.schemas.text2sql_schema import (
    BatchImportText2SQLRelationsRequest,
    CreateText2SQLRelationRequest,
    Text2SQLRelationBatchImportResponse,
    Text2SQLRelationItem,
    Text2SQLRelationListResponse,
    Text2SQLRelationTableColumnsResponse,
    UpdateText2SQLRelationRequest,
)
from services.text2sql import relation_service

router = APIRouter(tags=["Text2SQL"])


@router.get(
    "/relations",
    response_model=UnifiedResponse[Text2SQLRelationListResponse],
)
async def list_relations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    keyword: str = Query(default=""),
    table_name: str = Query(default=""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """分页查询关系列表（支持关键字与按表名过滤）。"""
    try:
        data = relation_service.list_relations(
            db,
            user_id=user_id,
            page=page,
            page_size=page_size,
            keyword=keyword,
            table_name=table_name,
        )
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Fetched relation list")


@router.post(
    "/relations",
    response_model=UnifiedResponse[Text2SQLRelationItem],
)
async def create_relation(
    request: CreateText2SQLRelationRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """新建一条表关系（自动去重，正/反向重复均会被拒绝）。"""
    try:
        data = relation_service.create_relation(db, request, user_id=user_id)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Created relation")


@router.post(
    "/relations/batch-import",
    response_model=UnifiedResponse[Text2SQLRelationBatchImportResponse],
)
async def batch_import_relations(
    request: BatchImportText2SQLRelationsRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """批量导入关系，返回新增/更新/跳过/失败统计。"""
    try:
        data = relation_service.batch_import_relations(db, request, user_id=user_id)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Batch imported relations")


@router.put(
    "/relations/{relation_id}",
    response_model=UnifiedResponse[Text2SQLRelationItem],
)
async def update_relation(
    relation_id: int,
    request: UpdateText2SQLRelationRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """更新指定关系（校验归属，去重时排除自身）。"""
    try:
        data = relation_service.update_relation(db, relation_id, request, user_id=user_id)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Updated relation")


@router.delete(
    "/relations/{relation_id}",
    response_model=UnifiedResponse[bool],
)
async def delete_relation(
    relation_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """删除指定关系（先校验归属）。"""
    try:
        relation_service.delete_relation(db, relation_id, user_id=user_id)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=True, message="Deleted relation")


@router.get(
    "/relations/table/{table_name}/columns",
    response_model=UnifiedResponse[Text2SQLRelationTableColumnsResponse],
)
async def get_relation_table_columns(
    table_name: str,
    db: Session = Depends(get_db),
):
    """获取某表字段清单（供配置关系时选择 JOIN 字段）。"""
    try:
        data = relation_service.get_table_columns(db, table_name)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Fetched table columns for relation")
