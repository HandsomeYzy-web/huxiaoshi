from fastapi import Request, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError

from core.logger import logger
from core.response import error

def register_exception_handlers(app: FastAPI):
    """
    注册全局异常捕获器，确保所有报错都以统一的 JSON 格式返回给前端
    """

    # 1. 捕获 FastAPI 标准的 HTTP 异常 (如主动 raise HTTPException)
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.warning(f"请求 {request.url.path} 触发业务异常: {exc.detail}")
        return error(code=exc.status_code, message=exc.detail)

    # 2. 捕获 Pydantic 参数校验异常 (如前端漏传必填参数、类型传错)
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # 提取具体的错误字段和信息
        errors = exc.errors()
        error_msg = "; ".join([f"{e['loc'][-1]}: {e['msg']}" for e in errors])
        logger.warning(f"请求 {request.url.path} 参数校验失败: {error_msg}")
        return error(code=422, message=f"参数校验失败: {error_msg}")

    # 3. 捕获数据库底层异常
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        logger.error(f"数据库执行异常: {exc}")
        return error(code=500, message="数据库内部服务错误")

    # 4. 兜底：捕获所有未被处理的未知崩溃 (防止抛出丑陋的 500 页面)
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"系统未知异常: {exc}") # logger.exception 会自动记录完整的堆栈
        return error(code=500, message="服务器内部错误，请联系管理员")