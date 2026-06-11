"""Text2SQL few-shot 历史样例服务（增强能力，按 TEXT2SQL_FEW_SHOT_ENABLED 开关启用）。

为 SQL 生成提供「相似问题示范样例」，采用两级数据源并优雅降级：
    1. 优先从专用的「few-shot 知识库」做向量检索（知识库隔离：只查这一个库），命中即用；
    2. 否则回流历史查询日志中「用户高分评价（如 5 星）且成功」的记录，
       先按候选表重叠过滤，再按问题语义相似度（余弦）排序，取 Top-N。
任何环节异常都安全退回「无历史样例」，绝不影响主流程。这是查询质量随使用量自我提升的闭环。
"""

from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy.orm import Session

from core.config import settings
from models.entities.text2sql_query_log import Text2SQLQueryLog
from repositories.elasticsearch_repo import es_repo
from repositories.text2sql_query_log_repo import Text2SQLQueryLogRepository
from services.embeddings import get_embeddings

_NO_EXAMPLES_TEXT = "(no historical examples)"


class Text2SQLFewShotService:
    """从知识库 / 历史日志构建 few-shot 上下文，并在失败时优雅降级。"""

    def __init__(self, max_examples: int = 3, candidate_limit: int = 200) -> None:
        self._max_examples = max(1, int(max_examples))
        self._candidate_limit = max(1, int(candidate_limit))

    @staticmethod
    def _normalize_identifier(value: str | None) -> str:
        text = (value or "").strip().strip("`").strip('"')
        if "." in text:
            text = text.split(".")[-1]
        return text.lower()

    @classmethod
    def _parse_selected_tables(cls, raw_value: str | None) -> set[str]:
        if not raw_value:
            return set()
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return set()
        if not isinstance(parsed, list):
            return set()
        normalized_tables: set[str] = set()
        for item in parsed:
            normalized = cls._normalize_identifier(str(item or ""))
            if normalized:
                normalized_tables.add(normalized)
        return normalized_tables

    @staticmethod
    def _safe_vector(values: Iterable[float] | None) -> list[float]:
        if values is None:
            return []
        try:
            return [float(item) for item in values]
        except (TypeError, ValueError):
            return []

    @classmethod
    def _cosine_similarity(cls, left: Iterable[float] | None, right: Iterable[float] | None) -> float:
        """计算两个向量的余弦相似度（维度不一致/零向量返回 0），用于按语义给历史样例排序。"""
        left_vector = cls._safe_vector(left)
        right_vector = cls._safe_vector(right)
        if not left_vector or not right_vector or len(left_vector) != len(right_vector):
            return 0.0
        dot = sum(a * b for a, b in zip(left_vector, right_vector))
        left_norm = sum(value * value for value in left_vector) ** 0.5
        right_norm = sum(value * value for value in right_vector) ** 0.5
        if left_norm <= 0.0 or right_norm <= 0.0:
            return 0.0
        return dot / (left_norm * right_norm)

    @staticmethod
    def _safe_positive_int(value: object) -> int | None:
        try:
            parsed = int(value) if value is not None else 0
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _is_feature_enabled() -> bool:
        return bool(getattr(settings, "TEXT2SQL_FEW_SHOT_ENABLED", False))

    def _resolve_fewshot_kb_id(self, db: Session) -> int:
        """解析 few-shot 专用知识库 ID：委托统一隔离规则（配置 ID 优先、名称兜底，无则 0=不启用）。"""
        from services.kb_scope import resolve_fewshot_kb_id

        return resolve_fewshot_kb_id(db)

    def _search_examples_from_kb(self, db: Session, question_text: str) -> str:
        """一级数据源：从 few-shot 知识库向量检索相似切片，去重后拼成示例文本（无库/无命中返回空串）。"""
        kb_id = self._resolve_fewshot_kb_id(db)
        if kb_id <= 0:
            return ""

        query_vector = list(get_embeddings().embed_query(question_text) or [])
        if not query_vector:
            return ""

        vector_dim = int(getattr(settings, "ES_VECTOR_DIM", 1024))
        if len(query_vector) != vector_dim:
            return ""

        raw_hits = es_repo.search_chunks(
            kb_id=kb_id,
            vector_dim=vector_dim,
            query_vector=query_vector,
            top_k=max(self._max_examples * 3, 8),
        )
        if not raw_hits:
            return ""

        lines: list[str] = []
        seen_texts: set[str] = set()
        idx = 1
        for hit in raw_hits:
            text = str(hit.get("text") or "").strip()
            if not text:
                continue
            normalized = text.lower()
            if normalized in seen_texts:
                continue
            seen_texts.add(normalized)

            compact_text = text if len(text) <= 1200 else text[:1197] + "..."
            lines.append(f"示例{idx}:")
            lines.append(f"  内容: {compact_text}")
            idx += 1
            if idx > self._max_examples:
                break

        return "\n".join(lines).strip()

    def search_similar_examples(
        self,
        db: Session,
        question: str,
        *,
        table_names: list[str] | None = None,
        table_name: str | None = None,
    ) -> str:
        """对外入口：为当前问题召回相似示范样例（知识库优先，否则回流高分历史查询）。"""
        if not self._is_feature_enabled():
            return _NO_EXAMPLES_TEXT

        question_text = str(question or "").strip()
        if not question_text:
            return _NO_EXAMPLES_TEXT

        # 一级：知识库向量检索；命中即返回，异常则静默降级到历史日志。
        try:
            kb_examples = self._search_examples_from_kb(db, question_text)
            if kb_examples:
                return kb_examples
        except Exception:  # noqa: BLE001
            pass

        # 仅把用户评分达到阈值（“非常满意”）的历史查询纳入 few-shot 示例池。
        # 评分为 NULL（未评分）的记录因 `feedback_score >= min_score` 为 NULL 而被自然排除。
        min_score = int(getattr(settings, "TEXT2SQL_FEWSHOT_MIN_SCORE", 5) or 0)
        try:
            Text2SQLQueryLogRepository(db).ensure_feedback_score_column()
        except Exception:  # noqa: BLE001
            pass
        query = (
            db.query(Text2SQLQueryLog)
            .filter(Text2SQLQueryLog.status == "success")
            .filter(Text2SQLQueryLog.final_sql.isnot(None))
            .filter(Text2SQLQueryLog.feedback_score >= min_score)
            .order_by(Text2SQLQueryLog.created_at.desc())
            .limit(self._candidate_limit)
        )
        logs = list(query.all())
        if not logs:
            return _NO_EXAMPLES_TEXT

        normalized_table_names = {
            self._normalize_identifier(item)
            for item in (table_names or [])
            if self._normalize_identifier(item)
        }
        if not normalized_table_names and table_name:
            normalized_single = self._normalize_identifier(table_name)
            if normalized_single:
                normalized_table_names.add(normalized_single)

        table_overlap_scores: dict[int, int] = {}
        if normalized_table_names:
            filtered_logs: list[Text2SQLQueryLog] = []
            for log in logs:
                selected_tables = self._parse_selected_tables(getattr(log, "selected_tables", None))
                overlap = len(selected_tables.intersection(normalized_table_names))
                if overlap <= 0:
                    continue
                filtered_logs.append(log)
                table_overlap_scores[int(getattr(log, "id", 0) or 0)] = overlap
            logs = filtered_logs
        elif table_name:
            table_key = self._normalize_identifier(table_name)
            logs = [
                log
                for log in logs
                if table_key in self._parse_selected_tables(getattr(log, "selected_tables", None))
            ]
        if not logs:
            return _NO_EXAMPLES_TEXT

        try:
            embedder = get_embeddings()
            question_vector = embedder.embed_query(question_text)
            scored_logs: list[tuple[float, Text2SQLQueryLog]] = []
            for log in logs:
                log_question = str(getattr(log, "question", "") or "").strip()
                if not log_question:
                    continue
                similarity = self._cosine_similarity(question_vector, embedder.embed_query(log_question))
                if similarity <= 0.0:
                    continue
                scored_logs.append((float(similarity), log))
        except Exception:  # noqa: BLE001
            scored_logs = [(1.0, log) for log in logs]

        if not scored_logs:
            return _NO_EXAMPLES_TEXT

        scored_logs.sort(
            key=lambda item: (
                -int(table_overlap_scores.get(int(getattr(item[1], "id", 0) or 0), 0)),
                -float(item[0]),
                -int(getattr(item[1], "id", 0)),
            )
        )
        examples = scored_logs[: self._max_examples]

        lines: list[str] = []
        for index, (_, log) in enumerate(examples, 1):
            sql_text = str(getattr(log, "final_sql", "") or "").strip()
            if not sql_text:
                continue
            lines.append(f"示例{index}:")
            lines.append(f"  问题: {str(getattr(log, 'question', '') or '').strip()}")
            lines.append(f"  SQL: {sql_text}")
        return "\n".join(lines) if lines else _NO_EXAMPLES_TEXT
