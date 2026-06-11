"""已废弃：请改用 services.text2sql.facade_service（本文件仅为向后兼容保留的旧适配层）。

历史上 Text2SQL 逻辑集中在本文件的 Text2SQLService 中；现已拆分为 services/text2sql/ 包下的
多个子服务，并由 facade_service 统一编排。此处仅保留薄适配，调用时会发出 DeprecationWarning。
"""

from __future__ import annotations

from warnings import warn

from sqlalchemy.orm import Session

from services.text2sql import config_service, facade_service


class Text2SQLService:
    """仅为向后兼容保留的旧适配器（请勿在新代码中使用）。"""

    def clear_schema_cache(self) -> None:
        """旧接口占位：在新架构下无操作（schema 由 schema_service 实时读取）。"""

    def query(
        self,
        question: str,
        db: Session | None = None,
        user_id: int | None = None,
    ) -> tuple[str, str, list[str], list[dict]]:
        warn(
            "Deprecated: use services.text2sql.facade_service instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if db is None:
            raise RuntimeError("Legacy Text2SQLService.query now requires db session")

        runtime_config = config_service.get_runtime_config(db, user_id=user_id)
        payload = facade_service.query(
            question,
            db,
            runtime_config=runtime_config,
            user_id=user_id,
        )
        return (
            str(payload.get("sql") or ""),
            str(payload.get("answer") or ""),
            list(payload.get("columns") or []),
            list(payload.get("rows") or []),
        )


text2sql_service = Text2SQLService()
