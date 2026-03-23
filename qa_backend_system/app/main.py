from fastapi import FastAPI
import uvicorn
from app.api.v1 import chat  # 引入我们刚写的 chat 路由

app = FastAPI(title="企业级智能问答系统 API", version="1.0.0")

# 注册路由，加上统一的前缀 /api/v1/chat
app.include_router(chat.router, prefix="/api/v1/chat", tags=["智能问答模块"])

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Backend system is running!"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)