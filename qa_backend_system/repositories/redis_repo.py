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

    def delete(self, key: str):
        if self.client is None:
            return
        self.client.delete(key)

    def ping(self) -> bool:
        if self.client is None:
            return False
        return bool(self.client.ping())


redis_repo = RedisRepo()
