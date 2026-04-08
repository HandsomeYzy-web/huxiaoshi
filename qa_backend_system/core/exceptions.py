from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.logger import logger
from core.response import error

# ============================================================
# Domain exceptions — raised in the Service layer.
# These carry no HTTP semantics; routers/handlers map them.
# ============================================================

class AppException(Exception):
    """Base class for all domain-level exceptions."""

    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(message)


class ResourceNotFoundError(AppException):
    """Resource does not exist or has been soft-deleted."""

    def __init__(self, message: str):
        super().__init__(message, code=404)


class DuplicateResourceError(AppException):
    """Uniqueness constraint violated (e.g. duplicate name)."""

    def __init__(self, message: str):
        super().__init__(message, code=400)


class BusinessError(AppException):
    """General business-rule violation."""

    def __init__(self, message: str):
        super().__init__(message, code=400)


class AuthenticationError(AppException):
    """Authentication failed (missing or invalid token)."""

    def __init__(self, message: str = "认证失败"):
        super().__init__(message, code=401)


class PermissionDeniedError(AppException):
    """Authenticated but not authorized for the resource."""

    def __init__(self, message: str = "无权限访问该资源"):
        super().__init__(message, code=403)


class ExternalServiceError(AppException):
    """External service (MinIO, Milvus, etc.) call failed."""

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
