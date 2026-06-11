import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import chat_router, file_router, kb_router, model_router, qa_router, text2sql_router
from core.config import settings
from core.database import init_db
from core.exceptions import register_exception_handlers
from core.logger import logger, setup_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logger()
    logger.info(f"正在启动 {settings.PROJECT_NAME} ...")
    init_db()

    from repositories.minio_repo import minio_repo  # noqa: F401
    from repositories.elasticsearch_repo import es_repo  # noqa: F401
    from repositories.redis_repo import redis_repo  # noqa: F401

    yield

    logger.info("服务已停止")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(kb_router.router, prefix=settings.API_V1_STR)
app.include_router(file_router.router, prefix=settings.API_V1_STR)
app.include_router(qa_router.router, prefix=settings.API_V1_STR)
app.include_router(chat_router.router, prefix=settings.API_V1_STR)
app.include_router(text2sql_router.router, prefix=settings.API_V1_STR)
app.include_router(model_router.router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "message": "系统运行正常。"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=os.getenv("UVICORN_RELOAD", "false").lower() == "true",
    )
