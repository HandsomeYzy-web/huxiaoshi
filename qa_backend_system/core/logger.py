import os
import sys
from loguru import logger

# 确保 logs 目录存在
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger():
    # 移除默认的控制台输出，防止重复打印
    logger.remove()

    # 1. 终端标准输出 (带有颜色和美化，方便本地开发调试)
    logger.add(
        sys.stdout,
        level="DEBUG",
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # 2. 常规日志文件存储 (Info 及以上级别)
    logger.add(
        os.path.join(LOG_DIR, "app_info.log"),
        level="INFO",
        rotation="500 MB",     # 日志文件达到 500MB 时自动切分创建一个新文件
        retention="30 days",   # 历史日志最多保留 30 天，自动清理旧日志
        encoding="utf-8",
        enqueue=True           # 开启异步写入，保证多线程/异步环境下的安全性
    )

    # 3. 错误日志独立存储 (Error 及以上级别)
    logger.add(
        os.path.join(LOG_DIR, "app_error.log"),
        level="ERROR",
        rotation="100 MB",
        retention="60 days",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,        # 记录完整的异常堆栈
        diagnose=True          # 诊断报错时的变量值 (生产环境视敏感度可关闭)
    )

# 在 main.py 启动时调用 setup_logger() 即可