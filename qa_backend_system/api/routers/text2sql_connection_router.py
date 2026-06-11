"""Text2SQL 数据库连接管理路由。

提供「被查询业务库」连接的查看 / 保存 / 连通性测试三个接口。返回体经脱敏，不含明文密码；
具体逻辑委托给 connection_service。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from core.exceptions import BusinessError
from core.response import UnifiedResponse, success
from models.schemas.text2sql_schema import (
    Text2SQLConnectionPayload,
    Text2SQLConnectionResponse,
    Text2SQLConnectionTestResponse,
)
from services.text2sql import connection_service

router = APIRouter(tags=["Text2SQL"])


@router.get(
    "/connection",
    response_model=UnifiedResponse[Text2SQLConnectionResponse],
)
async def get_text2sql_connection(db: Session = Depends(get_db)):
    """查看当前连接配置（脱敏，仅返回是否已设置密码）。"""
    return success(data=connection_service.get_public_connection(db), message="Fetched Text2SQL connection")


@router.put(
    "/connection",
    response_model=UnifiedResponse[Text2SQLConnectionResponse],
)
async def save_text2sql_connection(payload: Text2SQLConnectionPayload, db: Session = Depends(get_db)):
    """保存连接配置（保存前会先做连通性测试，密码加密落库）。"""
    try:
        data = connection_service.save_connection(db, payload)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Saved Text2SQL connection")


@router.post(
    "/connection/test",
    response_model=UnifiedResponse[Text2SQLConnectionTestResponse],
)
async def test_text2sql_connection(payload: Text2SQLConnectionPayload, db: Session = Depends(get_db)):
    """测试连接是否可连通（不落库）。"""
    try:
        connection_service.test_connection(db, payload)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(
        data=Text2SQLConnectionTestResponse(ok=True, message="Connection test passed"),
        message="Connection test passed",
    )
