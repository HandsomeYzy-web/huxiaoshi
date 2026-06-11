"""请求级公共依赖。

本应用自身不做鉴权：当前用户身份由上游统一认证平台（SSO 网关）通过请求头注入。
这里只保留一个依赖 `get_current_user_id`，作为将来对接统一认证平台的唯一改动点。
"""

from typing import Optional

from fastapi import Header

from core.config import settings


def get_current_user_id(
    x_user_id: Optional[str] = Header(None, alias=settings.CURRENT_USER_HEADER),
) -> int:
    """返回当前请求的用户 ID。

    - 由上游统一认证网关在请求头（默认 ``X-User-Id``）中注入。
    - 本地开发或缺失该请求头时，回退到 ``settings.DEFAULT_USER_ID``。
    - 聊天记录据此按用户区分；其它资源（知识库/文件/模型配置）为全局共享。
    """
    if x_user_id and x_user_id.strip().isdigit():
        return int(x_user_id.strip())
    return settings.DEFAULT_USER_ID
