import socket
import threading
import time
import webbrowser
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware # 新增：跨域中间件
import uvicorn
from rich.console import Console
from rich.panel import Panel

from app.api.v1 import chat
from app.core.logger import log
from app.models.schemas import success_resp, BaseResponse
from app.api.v1 import chat, knowledge # 引入 knowledge
from app.core.exceptions import register_exception_handlers
app = FastAPI(title="企业级智能问答系统 API", version="1.0.0")

# 激活全局异常拦截
register_exception_handlers(app)

# ==========================================
# 1. 配置 CORS 跨域（允许前端访问）
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段允许所有来源，生产环境建议改成前端的实际地址
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有请求方法 (GET, POST 等)
    allow_headers=["*"],  # 允许所有请求头
)


# ==========================================
# 2. 全局请求日志拦截器 (配合 Loguru)
# ==========================================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    # 记录请求进入
    log.info(f"👉 收到请求: {request.method} {request.url.path}")

    # 执行业务逻辑
    response = await call_next(request)

    # 记录请求耗时和状态码
    process_time = time.time() - start_time
    log.info(
        f"👈 请求完成: {request.method} {request.url.path} | 状态码: {response.status_code} | 耗时: {process_time:.3f}s")

    return response

# 挂载路由
app.include_router(chat.router, prefix="/api/v1/chat", tags=["智能问答模块"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["知识库管理"]) # 挂载知识库路由

@app.on_event("startup")
async def startup_event():
    log.info("🚀 智能问答系统后端服务正在启动...")


@app.on_event("shutdown")
async def shutdown_event():
    log.warning("🛑 智能问答系统后端服务已关闭。")


@app.get("/health", response_model=BaseResponse[dict])
def health_check():
    return success_resp(data={"status": "running", "version": "1.0.0"})


# ==========================================
# 下面是健壮的启动器辅助方法
# ==========================================

def is_port_in_use(port: int, host: str = '127.0.0.1') -> bool:
    """检测端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def get_free_port(start_port: int, host: str = '127.0.0.1') -> int:
    """自动寻找可用的空闲端口"""
    port = start_port
    while is_port_in_use(port, host):
        log.warning(f"⚠️ 端口 {port} 已被占用，正在尝试 {port + 1}...")
        port += 1
    return port


def print_banner(host: str, port: int):
    """打印漂亮的终端启动横幅"""
    console = Console()
    title = "[bold cyan]🚀 智能问答系统后端已就绪[/bold cyan]\n"
    docs_url = f"http://{host}:{port}/docs"
    health_url = f"http://{host}:{port}/health"

    info = f"📖 API 调试文档: [bold green][link={docs_url}]{docs_url}[/link][/bold green]\n"
    info += f"❤️ 健康检查接口: [link={health_url}]{health_url}[/link]"

    panel = Panel(title + info, title="Q&A System API", border_style="blue", expand=False)
    console.print(panel)


def auto_open_browser(host: str, port: int):
    """延迟 1.5 秒后自动打开浏览器（等待 Uvicorn 启动完毕）"""
    time.sleep(1.5)
    webbrowser.open(f"http://{host}:{port}/docs")


if __name__ == "__main__":
    host = "0.0.0.0"
    default_port = 8000

    # 1. 自动获取可用端口（防止 8000 被占导致崩溃）
    safe_port = get_free_port(default_port, host="127.0.0.1")

    # 2. 打印彩色欢迎面板
    print_banner("127.0.0.1", safe_port)

    # 3. 开启后台子线程，准备自动打开浏览器
    threading.Thread(target=auto_open_browser, args=("127.0.0.1", safe_port), daemon=True).start()

    # 4. 启动主服务
    # 注意：这里我们去掉了 reload=True，因为在生产级或自定义启动脚本中，
    # reload 会引发多进程重启，导致多次检测端口和打印面板。
    uvicorn.run("app.main:app", host=host, port=safe_port)