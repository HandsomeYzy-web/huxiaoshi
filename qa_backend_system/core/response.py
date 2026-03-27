from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse

# 定义一个泛型变量，用于代表 data 里面的具体内容
T = TypeVar("T")

class UnifiedResponse(BaseModel, Generic[T]):
    """
    统一响应的 Pydantic 模型 (仅用于生成 Swagger 文档)
    """
    code: int = Field(200, description="业务状态码，200 代表成功，非 200 代表有业务异常")
    message: str = Field("success", description="提示信息，如 '操作成功' 或错误详情")
    data: Optional[T] = Field(None, description="实际的业务数据")

def success(data: Any = None, message: str = "success") -> dict:
    """
    成功响应的快捷封装函数
    用法: return success(data=kb_list, message="查询知识库成功")
    """
    return {
        "code": 200,
        "message": message,
        "data": data
    }

def error(code: int = 400, message: str = "error", data: Any = None, http_status_code: int = 200) -> JSONResponse:
    """
    错误响应的快捷封装函数。
    通常在企业级开发中，无论业务成功与否，HTTP 状态码都固定返回 200，
    让前端去判断 JSON 内部的 code 来决定如何提示。
    """
    return JSONResponse(
        status_code=http_status_code,
        content={
            "code": code,
            "message": message,
            "data": data
        }
    )