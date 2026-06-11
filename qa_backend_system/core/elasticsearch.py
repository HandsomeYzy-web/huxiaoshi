"""
Elasticsearch 客户端管理模块：提供线程安全的单例 Elasticsearch 客户端。

Elasticsearch 客户端基于 HTTP，连接池由客户端内部维护，进程/线程安全，
因此全局复用一个实例即可（无需像 pymilvus 那样按进程重新建立连接）。
"""

import threading

from elasticsearch import Elasticsearch

from core.config import settings

# 线程锁，确保多线程环境下只初始化一次 Elasticsearch 客户端
_es_lock = threading.Lock()
_es_client: Elasticsearch | None = None


def _build_client() -> Elasticsearch:
    """根据配置构建 Elasticsearch 客户端，按需附加认证信息。"""
    kwargs: dict = {"hosts": [settings.ES_URL], "request_timeout": 30}
    if settings.ES_API_KEY:
        kwargs["api_key"] = settings.ES_API_KEY
    elif settings.ES_USERNAME:
        kwargs["basic_auth"] = (settings.ES_USERNAME, settings.ES_PASSWORD)
    return Elasticsearch(**kwargs)


def get_es_client() -> Elasticsearch:
    """返回全局 Elasticsearch 客户端（双重检查锁，线程安全的懒加载单例）。"""
    global _es_client
    if _es_client is None:
        with _es_lock:
            if _es_client is None:
                _es_client = _build_client()
    return _es_client
