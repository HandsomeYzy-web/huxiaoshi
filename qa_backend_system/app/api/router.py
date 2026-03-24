from fastapi import APIRouter
from app.api.v1 import chat, admin_kb

# 创建一个 v1 版本的总路由
api_router = APIRouter()

# 将子路由全部挂载到这个总路由上
api_router.include_router(chat.router, prefix="/chat", tags=["智能问答模块"])
api_router.include_router(admin_kb.router, prefix="/admin/kb", tags=["管理端-知识库维护"])