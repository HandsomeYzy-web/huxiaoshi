import os
import sys
from loguru import logger

# 确保日志文件夹存在
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 移除默认的控制台输出，重新配置
logger.remove()

# 1. 配置控制台输出 (带颜色和时间格式)
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# 2. 配置普通日志文件 (按天切割，保留30天)
logger.add(
    os.path.join(LOG_DIR, "app_{time:YYYY-MM-DD}.log"),
    rotation="00:00",
    retention="30 days",
    level="INFO",
    encoding="utf-8",
    enqueue=True # 异步写入，不阻塞主线程
)

# 3. 配置错误日志文件 (单独收集 Error 级别及以上的报错)
logger.add(
    os.path.join(LOG_DIR, "error_{time:YYYY-MM-DD}.log"),
    rotation="00:00",
    retention="30 days",
    level="ERROR",
    encoding="utf-8",
    enqueue=True
)

# 导出一个全局可用的日志对象
log = logger