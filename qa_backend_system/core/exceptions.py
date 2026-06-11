"""
全局异常定义与异常处理器注册模块。

本文件定义了业务层的自定义异常类（不含 HTTP 语义），
以及 FastAPI 全局异常捕获器，确保所有报错以统一 JSON 格式返回前端。
"""

from fastapi import Request, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError

from core.logger import logger
from core.response import error


# ============================================================
# Domain exceptions — raised in the Service layer.
# These carry no HTTP semantics; routers/handlers map them.
# ============================================================

class AppException(Exception):
    """基础业务异常类：所有自定义异常的父类，携带业务状态码和错误消息。"""

    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(message)


class ResourceNotFoundError(AppException):
    """资源不存在异常（404）。"""

    def __init__(self, message: str):
        super().__init__(message, code=404)


class DuplicateResourceError(AppException):
    """资源重复异常（如重复名称）。"""

    def __init__(self, message: str):
        super().__init__(message, code=400)


class BusinessError(AppException):
    """通用业务规则违规异常。"""

    def __init__(self, message: str):
        super().__init__(message, code=400)


class ExternalServiceError(AppException):
    """外部服务调用失败异常（MinIO、Elasticsearch 等）。"""

    def __init__(self, message: str):
        super().__init__(message, code=502)


# ============================================================
# FastAPI exception handlers
# ============================================================

def register_exception_handlers(app: FastAPI):
    """
    注册全局异常捕获器，确保所有报错都以统一的 JSON 格式返回给前端。
    """

    # 0. 领域异常（Service 层抛出，不含 HTTP 语义）
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        logger.warning(f"请求 {request.url.path} 触发领域异常: {exc.message}")
        return error(code=exc.code, message=exc.message)

    # 1. FastAPI 标准 HTTP 异常
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.warning(f"请求 {request.url.path} 触发业务异常: {exc.detail}")
        return error(code=exc.status_code, message=exc.detail)

    # 2. Pydantic 参数校验异常
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        error_msg = "; ".join([f"{e['loc'][-1]}: {e['msg']}" for e in errors])
        logger.warning(f"请求 {request.url.path} 参数校验失败: {error_msg}")
        return error(code=422, message=f"参数校验失败: {error_msg}")

    # 3. 数据库底层异常
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        logger.error(f"数据库执行异常: {exc}")
        return error(code=500, message="数据库内部服务错误")

    # 4. 兜底
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"系统未知异常: {exc}")
        return error(code=500, message="服务器内部错误，请联系管理员")