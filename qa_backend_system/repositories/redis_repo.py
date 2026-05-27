import json
from typing import Optional

import redis

from core.config import settings
from core.logger import logger


class RedisRepo:
    def __init__(self):
        self.client = None
        try:
            self.client = redis.Redis.from_url(
                settings.REDIS_URI,
                decode_responses=True,
            )
            self.client.ping()
        except Exception as exc:
            logger.error(f"Failed to connect Redis: {exc}")

    def set_json(self, key: str, value: dict, expire_seconds: int = 3600):
        if self.client is None:
            return
        self.client.setex(key, expire_seconds, json.dumps(value, ensure_ascii=False))

    def get_json(self, key: str) -> Optional[dict]:
        if self.client is None:
            return None
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None

    def set_list(self, key: str, values: list, expire_seconds: int = 300):
        """缓存字符串列表，如权限代码集合。"""
        if self.client is None:
            return
        self.client.setex(key, expire_seconds, json.dumps(values, ensure_ascii=False))

    def get_list(self, key: str) -> list | None:
        """读取字符串列表缓存，未命中返回 None。"""
        if self.client is None:
            return None
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None

    def delete(self, key: str):
        if self.client is None:
            return
        self.client.delete(key)

    def delete_pattern(self, pattern: str):
        """删除匹配 glob 模式的所有 key（慎用，仅用于小规模失效场景）。"""
        if self.client is None:
            return
        keys = self.client.keys(pattern)
        if keys:
            self.client.delete(*keys)

    def ping(self) -> bool:
        if self.client is None:
            return False
        return bool(self.client.ping())


redis_repo = RedisRepo()
