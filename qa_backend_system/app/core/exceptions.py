from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.logger import log
from app.models.schemas import error_resp


def register_exception_handlers(app: FastAPI):
    """
    注册全局异常处理器
    """

    # 1. 捕获 FastAPI 标准的 HTTP 异常 (如 404, 401, 403 等)
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        log.warning(f"⚠️ HTTP 异常 | 路径: {request.url.path} | 状态码: {exc.status_code} | 详情: {exc.detail}")
        # 返回我们统一的 BaseResponse 结构
        return JSONResponse(
            status_code=exc.status_code,
            content=error_resp(code=exc.status_code, msg=str(exc.detail)).model_dump()
        )

    # 2. 捕获 Pydantic 参数校验异常 (前端传错参数、少传参数时触发)
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # 提取第一个校验错误的信息，让提示更人性化
        errors = exc.errors()
        error_msg = f"参数校验失败: {errors[0].get('loc')[-1]} {errors[0].get('msg')}" if errors else "参数校验失败"

        log.warning(f"🚫 参数校验异常 | 路径: {request.url.path} | 详情: {errors}")

        return JSONResponse(
            status_code=422,
            content=error_resp(code=422, msg=error_msg).model_dump()
        )

    # 3. 捕获所有未预料到的系统异常 (终极兜底 500 错误)
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # exc_info=True 会在日志中打印完整的错误栈，非常利于排查 bug
        log.error(f"💥 系统内部异常 | 路径: {request.url.path} | 错误信息: {str(exc)}", exc_info=True)

        # 无论后端报什么错，对外永远只返回友好的提示，不泄露系统信息
        return JSONResponse(
            status_code=500,
            content=error_resp(code=500, msg="服务器内部错误，请联系系统管理员。").model_dump()
        )