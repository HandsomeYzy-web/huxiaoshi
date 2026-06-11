"""知识库隔离（scope）规则：text2SQL 专用知识库与文档问答知识库相互隔离。

- 表路由：text2SQL 查表时仅检索「table_desc」用途的知识库；
- few-shot：text2SQL 召回历史样例时仅检索「few_shot」用途的知识库；
- 文档问答：可检索除上述两类保留库之外的所有知识库。

保留库的识别依据（按优先级）：
    1. 知识库的 purpose 字段（新建知识库时由用户选择，table_desc / few_shot 全局各一个）；
    2. ID 配置（TABLE_ROUTE_KB_ID / TEXT2SQL_FEWSHOT_KB_ID，运维级显式覆盖）；
    3. 名称匹配兜底（TEXT2SQL_TABLE_DESC_KB_NAME / TEXT2SQL_FEWSHOT_KB_NAME，
       兼容 purpose 字段出现之前按名称约定创建的老库）。
名称比较忽略大小写、首尾空白，并把 ``-`` 与 ``_`` 视为等价（few-shot 等同 few_shot）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.config import settings
from models.entities import KnowledgeBase
from repositories.kb_repo import KBRepo

# 知识库用途取值（与 kb_schema.KBPurpose、knowledge_base.purpose 列保持一致）
PURPOSE_DOCUMENT = "document"
PURPOSE_TABLE_DESC = "table_desc"
PURPOSE_FEW_SHOT = "few_shot"
RESERVED_PURPOSES = {PURPOSE_TABLE_DESC, PURPOSE_FEW_SHOT}


def normalize_kb_name(name: object) -> str:
    """归一化知识库名称用于比较：去空白、转小写、- 与 _ 等价。"""
    return str(name or "").strip().lower().replace("-", "_")


def _safe_positive_int(value: object) -> int:
    try:
        parsed = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _kb_purpose(kb: KnowledgeBase) -> str:
    return str(getattr(kb, "purpose", "") or PURPOSE_DOCUMENT).strip().lower()


def _reserved_kb_names() -> set[str]:
    names = {
        normalize_kb_name(getattr(settings, "TEXT2SQL_TABLE_DESC_KB_NAME", "")),
        normalize_kb_name(getattr(settings, "TEXT2SQL_FEWSHOT_KB_NAME", "")),
    }
    return {name for name in names if name}


def _reserved_kb_ids_from_config() -> set[int]:
    ids = {
        _safe_positive_int(getattr(settings, "TABLE_ROUTE_KB_ID", 0)),
        _safe_positive_int(getattr(settings, "TEXT2SQL_FEWSHOT_KB_ID", 0)),
    }
    return {kb_id for kb_id in ids if kb_id}


def is_reserved_kb(kb: KnowledgeBase) -> bool:
    """该知识库是否为 text2SQL 保留库（table_desc / few_shot），文档问答不可检索。"""
    if _kb_purpose(kb) in RESERVED_PURPOSES:
        return True
    if _safe_positive_int(getattr(kb, "id", 0)) in _reserved_kb_ids_from_config():
        return True
    return normalize_kb_name(getattr(kb, "name", "")) in _reserved_kb_names()


def filter_document_kbs(kbs: list[KnowledgeBase]) -> list[KnowledgeBase]:
    """文档问答可用知识库：剔除 text2SQL 保留库。"""
    return [kb for kb in kbs if not is_reserved_kb(kb)]


def get_document_kb_ids(db: Session) -> list[int]:
    """文档问答可检索的全部知识库 ID（已剔除保留库）。"""
    return [kb.id for kb in filter_document_kbs(KBRepo(db).get_all_kbs())]


def _resolve_reserved_kb_id(db: Session, purpose: str, id_key: str, name_key: str) -> int:
    """解析某个保留库的 ID：purpose 字段 > 配置 ID > 名称匹配兜底；未找到返回 0。"""
    repo = KBRepo(db)

    by_purpose = repo.get_kbs_by_purpose(purpose)
    if by_purpose:
        return int(by_purpose[0].id)

    configured_id = _safe_positive_int(getattr(settings, id_key, 0))
    if configured_id and repo.get_kb_by_id(configured_id) is not None:
        return configured_id

    target_name = normalize_kb_name(getattr(settings, name_key, ""))
    if not target_name:
        return 0
    for kb in repo.get_all_kbs():
        if normalize_kb_name(getattr(kb, "name", "")) == target_name:
            return int(kb.id)
    return 0


def resolve_table_desc_kb_id(db: Session) -> int:
    """解析 text2SQL 表路由专用的 table_desc 知识库 ID（未找到返回 0，表示不启用）。"""
    return _resolve_reserved_kb_id(
        db, PURPOSE_TABLE_DESC, "TABLE_ROUTE_KB_ID", "TEXT2SQL_TABLE_DESC_KB_NAME"
    )


def resolve_fewshot_kb_id(db: Session) -> int:
    """解析 text2SQL few-shot 专用知识库 ID（未找到返回 0，表示不启用）。"""
    return _resolve_reserved_kb_id(
        db, PURPOSE_FEW_SHOT, "TEXT2SQL_FEWSHOT_KB_ID", "TEXT2SQL_FEWSHOT_KB_NAME"
    )
