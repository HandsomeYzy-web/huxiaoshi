from celery import Celery
from celery.signals import worker_process_init
from core.config import settings
from core.elasticsearch import get_es_client

# 1. 初始化 Celery 实例
# 第一个参数是当前模块的名称，这里命名为 "qa_backend_tasks"
# broker: 消息中间件，我们使用 Redis 接收 FastAPI 发来的任务
# backend: 结果存储，同样使用 Redis 存储任务执行的最终状态
celery_app = Celery(
    "qa_backend_tasks",
    broker=settings.REDIS_URI,
    backend=settings.REDIS_URI,
    # 显式包含定义了具体任务的模块，方便 Celery Worker 启动时自动加载
    include=["tasks.document_tasks"]
)

# 2. 配置 Celery 的运行参数
celery_app.conf.update(
    # 任务序列化格式
    task_serializer="json",
    # 结果序列化格式
    result_serializer="json",
    # 允许接收的内容类型
    accept_content=["json"],
    # 时区设置，与我们 MySQL 的设置保持一致
    timezone="Asia/Shanghai",
    enable_utc=False,

    # 任务执行时间限制 (防止某个损坏的 PDF 解析死循环卡死整个队列)
    # hard_time_limit: 强制杀掉进程的时间 (例如 30 分钟)
    # soft_time_limit: 抛出异常的时间 (例如 25 分钟，允许捕获并做善后处理)
    task_time_limit=1800,
    task_soft_time_limit=1500,

    # 每个 worker 进程在执行完一定数量任务后重启，防止内存泄漏 (特别是处理图像和深度学习模型时)
    worker_max_tasks_per_child=50
)


@worker_process_init.connect
def init_worker_es_connection(**kwargs):
    """
    Celery Worker 进程启动时初始化 Elasticsearch 客户端并做一次连通性探测。

    Elasticsearch 客户端基于 HTTP，连接池由客户端内部维护，无需像 pymilvus 那样
    为每个 Worker 进程单独建立全局连接；这里仅 ping 一次以便尽早发现配置/网络问题。
    探测失败不阻断 Worker 启动（ES 可能稍后就绪，客户端会自动重连）。
    """
    from core.logger import logger

    try:
        get_es_client().info()
        logger.info(f"[Worker 初始化] Elasticsearch 连接已就绪: {settings.ES_URL}")
    except Exception as e:
        logger.warning(f"[Worker 初始化] Elasticsearch 连通性探测失败（将在任务执行时重试）: {e}")


if __name__ == "__main__":
    # 允许直接通过 python tasks/celery_app.py 测试启动
    celery_app.start()
