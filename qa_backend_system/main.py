from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.logger import setup_logger, logger
from core.database import init_db

# 这里预先导入路由包，稍后我们会去完善它们
from api.routers import kb_router, file_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理
    yield 之前的部分会在服务启动前执行
    yield 之后的部分会在服务关闭时执行
    """
    # 1. 初始化日志系统
    setup_logger()
    logger.info(f"🚀 {settings.PROJECT_NAME} 服务正在启动...")

    # 2. 初始化数据库表结构 (自动在 MySQL 中建表)
    init_db()

    # 3. 检查其他单例连接 (Milvus, MinIO, Redis 会在首次导入时自动连接并打印日志)
    from repositories.minio_repo import minio_repo
    from repositories.milvus_repo import milvus_repo
    from repositories.redis_repo import redis_repo

    yield  # 应用在此处保持运行

    # 停机时的清理逻辑可以写在这里
    logger.info("🛑 服务已安全关闭。")


# ==========================================
# 初始化 FastAPI 实例
# ==========================================
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# ==========================================
# 配置跨域资源共享 (CORS)
# 允许前端 (如 React/Vue 或 Streamlit) 跨域调用接口
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议替换为具体的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 挂载业务路由
# ==========================================
app.include_router(kb_router.router, prefix=settings.API_V1_STR)
app.include_router(file_router.router, prefix=settings.API_V1_STR)


# ==========================================
# 基础健康检查接口
# ==========================================
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "message": "System is running gracefully."}


if __name__ == "__main__":
    import uvicorn

    # 本地开发启动方式 (生产环境通常用 uvicorn 命令启动)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)