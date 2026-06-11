"""Text2SQL 共享分词工具：中文 2-gram + 英文/数字 token 切分。

facade / vector / schema-prune 等模块统一复用，避免逻辑重复。
"""

from __future__ import annotations

import re

_QUESTION_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[一-鿿]+")


def contains_chinese(value: str) -> bool:
    """判断字符串中是否包含中文字符（用于决定是否走中文 2-gram 切分）。"""
    return any("一" <= char <= "鿿" for char in str(value or ""))


def build_search_tokens(text: str, *, max_tokens: int = 256) -> set[str]:
    """把文本切成检索用 token 集合：英文按下划线/空格拆分，中文额外加 2-gram。"""
    token_set: set[str] = set()
    for raw in _QUESTION_TOKEN_PATTERN.findall(str(text or "").lower()):
        token = str(raw or "").strip().strip("_")
        if not token:
            continue

        if contains_chinese(token):
            compact = token.replace("_", "")
            if compact:
                token_set.add(compact)
            if len(compact) >= 2:
                # 中文用 2-gram，避免整句作为单一 token 难以命中。
                max_grams = min(len(compact) - 1, 64)
                for index in range(max_grams):
                    token_set.add(compact[index : index + 2])
        else:
            for part in re.split(r"[_\s]+", token):
                normalized = part.strip()
                if len(normalized) >= 2:
                    token_set.add(normalized)
            if len(token) >= 2:
                token_set.add(token)

        if len(token_set) >= max_tokens:
            break
    return token_set
