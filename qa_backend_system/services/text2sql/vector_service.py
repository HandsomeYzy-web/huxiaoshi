"""Text2SQL 表级向量召回服务（增强能力，路由库按 TABLE_ROUTE_KB_ID 或 table_desc 名称解析）。

知识库隔离：表路由只检索专用的「table_desc」知识库（ID 配置优先、名称兜底），
不会触碰文档问答的其他知识库。借助该路由库做语义召回，为表路由提供语义相关性分数：
把用户问题向量化后到 ES 检索知识库切片，再用切片文本与各候选表的
「术语集合（表名 + 画像分词）」做重叠匹配，折算出每张表的语义得分。

为降噪做了多重处理：过滤跨表高频共享词（区分度低）、对命中过多表的宽泛切片做多样性惩罚、
按术语重叠度分级加权，最后用「最大分 + 额外信号 + 命中次数」融合成单表得分。
未配置知识库或检索失败时安全返回空分数（路由退化为关键词/画像打分）。
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict

from sqlalchemy.orm import Session

from core.config import settings
from models.entities.knowledge_file import KnowledgeFile
from repositories.kb_repo import KBRepo as KnowledgeBaseRepository
from repositories.elasticsearch_repo import es_repo
from services.embeddings import get_embeddings
from services.text2sql.text_tokens import build_search_tokens, contains_chinese

_logger = logging.getLogger("text2sql.vector")


class Text2SQLVectorService:
    """为表路由提供「表级语义召回」得分。"""

    def __init__(self, kb_id: int | None = 0):
        # 未配置路由知识库时取 0，表示不启用向量召回。
        self.kb_id = self._safe_positive_int(kb_id) or 0

    @staticmethod
    def _normalize_identifier(value: str | None) -> str:
        text = (value or "").strip().strip("`").strip('"')
        if "." in text:
            text = text.split(".")[-1]
        return text.lower()

    @staticmethod
    def _contains_chinese(value: str) -> bool:
        return contains_chinese(value)

    @classmethod
    def _tokenize_terms(cls, text: str, *, max_terms: int = 256) -> set[str]:
        return build_search_tokens(text, max_tokens=max_terms)

    @staticmethod
    def _normalize_similarity(value: float | int | None) -> float:
        score = float(value or 0.0)
        if score <= 0:
            return 0.0
        return max(0.0, min(1.0, score))

    @classmethod
    def _build_table_terms(cls, normalized_table: str, profile_text: str) -> set[str]:
        meaningful_terms = cls._tokenize_terms(normalized_table, max_terms=64)
        if profile_text:
            meaningful_terms.update(cls._tokenize_terms(profile_text, max_terms=192))
        if normalized_table:
            meaningful_terms.add(normalized_table)
        return meaningful_terms

    @staticmethod
    def _build_non_informative_terms(term_index: dict[str, set[str]], table_count: int) -> set[str]:
        """Filter out overly-shared tokens to reduce cross-table noise."""
        if table_count <= 1:
            return set()
        shared_threshold = max(2, int(math.ceil(float(table_count) * 0.35)))
        return {
            term
            for term, linked_tables in term_index.items()
            if len(linked_tables) >= shared_threshold
        }

    @staticmethod
    def _safe_int(value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_positive_int(value: object) -> int | None:
        try:
            parsed = int(value) if value is not None else 0
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _load_file_name_lookup(db: Session, file_ids: set[int]) -> dict[int, str]:
        if not file_ids:
            return {}
        rows = (
            db.query(KnowledgeFile.id, KnowledgeFile.file_name)
            .filter(KnowledgeFile.id.in_(sorted(file_ids)))
            .all()
        )
        return {int(file_id): str(file_name or "") for file_id, file_name in rows}

    def _resolve_route_kb(self, db: Session, requested_kb_id: int | None = None) -> tuple[int, object | None]:
        """解析本次使用的路由知识库：入参指定 > 构造时配置 > 按名称解析 table_desc 库。

        知识库隔离：表路由只允许检索 table_desc 专用库，都解析不到则返回 (0, None) 表示不启用。
        """
        repo = KnowledgeBaseRepository(db)

        get_by_id = getattr(repo, "get_by_id", None) or getattr(repo, "get_kb_by_id", None)
        if not callable(get_by_id):
            return 0, None

        explicit_kb_id = self._safe_positive_int(requested_kb_id)
        if explicit_kb_id:
            kb = get_by_id(explicit_kb_id)
            if kb is not None:
                return explicit_kb_id, kb

        configured_kb_id = self._safe_positive_int(self.kb_id)
        if configured_kb_id:
            kb = get_by_id(configured_kb_id)
            if kb is not None:
                return configured_kb_id, kb

        from services.kb_scope import resolve_table_desc_kb_id

        fallback_kb_id = self._safe_positive_int(resolve_table_desc_kb_id(db))
        if fallback_kb_id:
            kb = get_by_id(fallback_kb_id)
            if kb is not None:
                return fallback_kb_id, kb

        return 0, None

    def search_tables(
        self,
        db: Session,
        question: str,
        *,
        candidate_tables: list[str],
        top_k: int = 15,
        candidate_profiles: dict[str, str] | None = None,
        route_kb_id: int | None = None,
    ) -> dict[str, float]:
        """对候选表做语义召回打分，返回 {表名: [0,1] 归一化得分}。

        流程：问题向量化 → ES 向量检索知识库切片 → 切片文本分词后与各表术语集合做重叠匹配 →
        过滤高频共享词、按重叠度分级加权、对宽泛命中做多样性惩罚 → 融合出单表得分。
        任意前置条件不满足（无问题/无候选/知识库缺失/维度不符/检索异常）均安全返回空字典。
        """
        question_text = str(question or "").strip()
        if not question_text or not candidate_tables:
            return {}

        active_kb_id, kb = self._resolve_route_kb(db, requested_kb_id=route_kb_id)
        if kb is None or active_kb_id <= 0:
            # 名称解析默认开启后，未创建 table_desc 库属正常配置，降级为关键词/画像路由即可。
            _logger.debug(
                "Vector route KB not found: requested_kb_id=%s configured_kb_id=%s",
                route_kb_id,
                self.kb_id,
            )
            return {}

        try:
            query_vector = list(get_embeddings().embed_query(question_text) or [])
            if not query_vector:
                return {}
            expected_dim = int(settings.ES_VECTOR_DIM)
            if len(query_vector) != expected_dim:
                _logger.warning(
                    "Vector dim mismatch for routing: expected=%s actual=%s",
                    expected_dim,
                    len(query_vector),
                )
                return {}

            query_limit = max(int(top_k) * 8, 40)
            raw_hits = es_repo.search_chunks(
                kb_id=active_kb_id,
                vector_dim=expected_dim,
                query_vector=query_vector,
                top_k=query_limit,
            )
        except Exception:  # noqa: BLE001
            _logger.exception(
                "Vector search failed for kb_id=%s requested_kb_id=%s",
                active_kb_id,
                route_kb_id,
            )
            return {}

        profile_lookup = {
            self._normalize_identifier(table_name): str(profile_text or "")
            for table_name, profile_text in (candidate_profiles or {}).items()
        }
        table_lookup: dict[str, str] = {}
        table_terms: dict[str, set[str]] = {}
        term_index: dict[str, set[str]] = defaultdict(set)
        for table_name in candidate_tables:
            normalized = self._normalize_identifier(table_name)
            if not normalized:
                continue
            table_lookup[normalized] = table_name
            profile_text = profile_lookup.get(normalized, "")
            terms = self._build_table_terms(normalized, profile_text)
            table_terms[normalized] = terms
            for term in terms:
                term_index[term].add(normalized)

        if not table_lookup:
            return {}
        non_informative_terms = self._build_non_informative_terms(term_index, len(table_lookup))
        table_terms_for_match: dict[str, set[str]] = {}
        for normalized_table, terms in table_terms.items():
            filtered_terms = {
                term
                for term in terms
                if term == normalized_table or term not in non_informative_terms
            }
            table_terms_for_match[normalized_table] = filtered_terms or terms

        file_ids: set[int] = set()
        for hit in raw_hits:
            file_id = self._safe_int(hit.get("file_id"))
            if file_id is not None and file_id > 0:
                file_ids.add(file_id)
        file_name_lookup = self._load_file_name_lookup(db, file_ids)

        score_max: dict[str, float] = {}
        score_sum: dict[str, float] = defaultdict(float)
        score_hits: dict[str, int] = defaultdict(int)

        for hit in raw_hits:
            hit_text = str(hit.get("text") or "")
            base_score = self._normalize_similarity(hit.get("score"))
            if base_score <= 0:
                continue

            source_parts = [hit_text]
            file_id = self._safe_int(hit.get("file_id"))
            if file_id is not None and file_id > 0:
                file_name = file_name_lookup.get(file_id, "")
                if file_name:
                    source_parts.append(file_name)
            source_text = " ".join(part for part in source_parts if part).strip()
            if not source_text:
                continue

            text_terms = self._tokenize_terms(source_text, max_terms=512)
            if not text_terms:
                continue
            informative_text_terms = {
                term
                for term in text_terms
                if term not in non_informative_terms
            }
            if not informative_text_terms:
                continue

            matched_tables: set[str] = set()
            for term in informative_text_terms:
                matched_tables.update(term_index.get(term, set()))
            if not matched_tables:
                continue
            # Penalize broad hits that match too many tables, to reduce routing noise.
            diversity_penalty = 1.0
            if len(matched_tables) > 3:
                diversity_penalty = max(0.01, 3.0 / float(len(matched_tables)))

            for normalized_table in matched_tables:
                terms = table_terms_for_match.get(normalized_table, set())
                if not terms:
                    continue

                overlap = len(terms.intersection(informative_text_terms))
                if overlap <= 0:
                    continue

                if normalized_table in informative_text_terms:
                    factor = 1.0
                elif overlap >= 4:
                    factor = 0.85
                elif overlap >= 2:
                    factor = 0.72
                else:
                    factor = 0.56

                score = round(base_score * factor * diversity_penalty, 6)
                if score <= 0:
                    continue

                real_table = table_lookup.get(normalized_table)
                if not real_table:
                    continue
                score_max[real_table] = round(max(score_max.get(real_table, 0.0), score), 6)
                score_sum[real_table] = float(score_sum.get(real_table, 0.0)) + score
                score_hits[real_table] = int(score_hits.get(real_table, 0)) + 1

        blended_scores: dict[str, float] = {}
        for table_name, max_score in score_max.items():
            total_score = float(score_sum.get(table_name, 0.0))
            hit_count = int(score_hits.get(table_name, 0))
            extra_signal = max(0.0, total_score - float(max_score))
            blended = (
                float(max_score)
                + min(0.35, extra_signal * 0.3)
                + min(0.15, float(hit_count) * 0.03)
            )
            blended_scores[table_name] = round(max(0.0, min(1.0, blended)), 6)

        return blended_scores


