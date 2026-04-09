import redis
import json
from typing import Any, Optional
from core.config import settings
from core.logger import logger

class RedisRepo:
    """Redis 缓存层封装"""

    def __init__(self):
        self.client = redis.Redis.from_url(
            settings.REDIS_URI,
            decode_responses=True # 自动将 bytes 解码为 str
        )

    def init(self):
        """启动时显式初始化：验证 Redis 连接可用。"""
        try:
            self.client.ping()
        except Exception as e:
            logger.error(f"连接 Redis 失败: {e}")

    def set_json(self, key: str, value: dict, expire_seconds: int = 3600):
        """将字典存为 JSON 字符串"""
        self.client.setex(key, expire_seconds, json.dumps(value, ensure_ascii=False))

    def get_json(self, key: str) -> Optional[dict]:
        """获取 JSON 并解析为字典"""
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None

    def delete(self, key: str):
        self.client.delete(key)

redis_repo = RedisRepo() # 实例化单例