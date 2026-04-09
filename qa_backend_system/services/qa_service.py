"""
QA Service — hybrid retrieval-augmented generation pipeline.

Uses a combination of vector search (Milvus) and BM25-style keyword search
(MySQL) to produce a merged, deduplicated, and reranked result set.

The retrieval step is encapsulated as a LangChain RunnableLambda so it can be
composed into any LCEL chain.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Generator

from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from sqlalchemy.orm import Session

from core.config import settings
from models.schemas.qa_schema import (
    ChatAskRequest,
    ChatAskResponse,
    CitationItem,
    QAAskRequest,
    QAAskResponse,
)
from repositories.kb_repo import KBRepo
from repositories.file_repo import FileRepo
from repositories.milvus_repo import milvus_repo
from services.embeddings import get_embeddings
from services.llm_service import llm_service
from services.reranker_service import reranker_service


class QAService:
    def ask(self, db: Session, request: QAAskRequest) -> QAAskResponse:
        repo = KBRepo(db)
        target_kb_ids = self._resolve_target_kb_ids(repo, request.kb_id, request.kb_ids)
        top_k = request.top_k or settings.DEFAULT_RETRIEVAL_TOP_K

        docs = self._make_retriever(db, target_kb_ids, top_k).invoke(request.question)
        citations = [self._doc_to_citation(doc) for doc in docs]
        contexts = [self._doc_to_context(doc) for doc in docs]

        answer, model_used = llm_service.generate_answer(request.question, contexts)
        return QAAskResponse(
            answer=answer,
            citations=citations,
            retrieved_count=len(citations),
            model_used=model_used,
        )

    def retrieve(self, db: Session, request: QAAskRequest) -> QAAskResponse:
        repo = KBRepo(db)
        target_kb_ids = self._resolve_target_kb_ids(repo, request.kb_id, request.kb_ids)
        top_k = request.top_k or settings.DEFAULT_RETRIEVAL_TOP_K

        docs = self._make_retriever(db, target_kb_ids, top_k).invoke(request.question)
        citations = [self._doc_to_citation(doc) for doc in docs]
        return QAAskResponse(
            answer="",
            citations=citations,
            retrieved_count=len(citations),
            model_used=None,
        )

    def chat(self, db: Session, request: ChatAskRequest) -> ChatAskResponse:
        repo = KBRepo(db)
        knowledge_bases = repo.get_all_kbs()
        if not knowledge_bases:
            raise ValueError("No knowledge bases available")

        kb_map = {kb.id: kb for kb in knowledge_bases}
        top_k = request.top_k or settings.DEFAULT_RETRIEVAL_TOP_K

        docs = self._make_retriever(db, None, top_k).invoke(request.question)
        citations = [self._doc_to_citation(doc) for doc in docs]
        contexts = [self._doc_to_context(doc) for doc in docs]

        answer, model_used = llm_service.generate_answer(request.question, contexts)
        return ChatAskResponse(
            answer=answer,
            citations=citations,
            retrieved_count=len(citations),
            queried_kb_count=len(kb_map),
            queried_kb_ids=list(kb_map.keys()),
            model_used=model_used,
        )

    def stream_chat(
        self, db: Session, request: ChatAskRequest
    ) -> Generator[tuple[str, bool, str | None, list[CitationItem]], None, None]:
        """
        流式聊天。生成器协议：
        - 首次 yield：citations（引用列表）
        - 后续 yield：LLM 文本块 或 模型名称标记
        """
        repo = KBRepo(db)
        knowledge_bases = repo.get_all_kbs()
        if not knowledge_bases:
            raise ValueError("No knowledge bases available")

        top_k = request.top_k or settings.DEFAULT_RETRIEVAL_TOP_K

        docs = self._make_retriever(db, None, top_k).invoke(request.question)
        citations = [self._doc_to_citation(doc) for doc in docs]
        contexts = [self._doc_to_context(doc) for doc in docs]

        # First: send citations in one shot
        yield "", False, None, citations

        # Then: stream answer chunks
        for chunk, is_model_info, model_name in llm_service.stream_answer(request.question, contexts):
            yield chunk, is_model_info, model_name, []

    # ------------------------------------------------------------------
    # BM25-style keyword extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(question: str) -> list[str]:
        """Extract meaningful keywords from the question for BM25 keyword search."""
        # Remove common Chinese stop words and punctuation, split into tokens
        # Simple approach: split by non-word chars, filter short tokens
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', question)
        # Filter out very short tokens (single char Chinese, very short english)
        keywords = [t for t in tokens if len(t) >= 2]
        return keywords[:5]  # Limit to top 5 keywords

    # ------------------------------------------------------------------
    # LangChain retriever factory (hybrid: vector + BM25)
    # ------------------------------------------------------------------

    def _make_retriever(
        self,
        db: Session,
        kb_ids: list[int] | None,
        top_k: int,
        score_threshold: float = 0.0,
    ) -> RunnableLambda:
        """
        Returns a LangChain RunnableLambda that performs hybrid retrieval:
        1. Vector search via Milvus (semantic similarity)
        2. BM25-style keyword search via MySQL (lexical matching)
        3. Reciprocal Rank Fusion (RRF) to merge results
        4. Optional reranking

        When a single KB is targeted, its own retrieval_top_k / retrieval_score_threshold
        config takes precedence over the caller-supplied defaults.
        """

        _top_k = top_k
        _score_threshold = score_threshold
        _enable_rerank = False
        if kb_ids and len(kb_ids) == 1:
            _repo = KBRepo(db)
            _kb = _repo.get_kb_by_id(kb_ids[0])
            if _kb:
                _top_k = _kb.retrieval_top_k
                _score_threshold = _kb.retrieval_score_threshold
                _enable_rerank = _kb.enable_rerank

        def retrieve(question: str) -> list[Document]:
            query_vector = get_embeddings().embed_query(question)
            kb_repo = KBRepo(db)
            file_repo = FileRepo(db)

            # 启用 rerank 时先多取候选集
            fetch_k = _top_k * 3 if _enable_rerank else _top_k * 2

            # ── 1. Vector search (Milvus) ─────────────────────────
            if kb_ids and len(kb_ids) == 1:
                vector_results = milvus_repo.search_chunks(kb_ids[0], query_vector, top_k=fetch_k)
            elif kb_ids:
                vector_results = milvus_repo.search_chunks_across_kbs(kb_ids, query_vector, top_k=fetch_k)
            else:
                # No kb_ids specified — need to get all KB ids
                all_kbs = kb_repo.get_all_kbs()
                all_kb_ids = [kb.id for kb in all_kbs]
                if not all_kb_ids:
                    vector_results = []
                else:
                    vector_results = milvus_repo.search_chunks_across_kbs(all_kb_ids, query_vector, top_k=fetch_k)

            # Apply score threshold filter
            if _score_threshold > 0.0:
                vector_results = [r for r in vector_results if float(r.get("distance", 0.0)) >= _score_threshold]

            # ── 2. BM25-style keyword search (MySQL) ──────────────
            keywords = self._extract_keywords(question)
            bm25_chunks = []
            if keywords:
                keyword_str = keywords[0]  # Use primary keyword for LIKE search
                if kb_ids and len(kb_ids) == 1:
                    bm25_chunks = file_repo.search_chunks_by_keyword(kb_ids[0], keyword_str, limit=fetch_k)
                elif kb_ids:
                    # Search across specific KBs
                    for kid in kb_ids:
                        bm25_chunks.extend(file_repo.search_chunks_by_keyword(kid, keyword_str, limit=fetch_k))
                else:
                    bm25_chunks = file_repo.search_chunks_by_keyword_across_kbs(keyword_str, limit=fetch_k)

                # Try additional keywords if first keyword yields few results
                if len(bm25_chunks) < 3 and len(keywords) > 1:
                    for kw in keywords[1:3]:
                        if kb_ids and len(kb_ids) == 1:
                            extra = file_repo.search_chunks_by_keyword(kb_ids[0], kw, limit=fetch_k // 2)
                        else:
                            extra = file_repo.search_chunks_by_keyword_across_kbs(kw, limit=fetch_k // 2)
                        seen_ids = {c.id for c in bm25_chunks}
                        bm25_chunks.extend([c for c in extra if c.id not in seen_ids])

            # ── 3. Reciprocal Rank Fusion (RRF) ──────────────────
            # Build chunk_id -> score maps
            rrf_k = 60  # RRF constant
            chunk_scores: dict[int, float] = defaultdict(float)
            chunk_data: dict[int, dict] = {}

            # Vector results contribution
            for rank, item in enumerate(vector_results):
                entity = item["entity"]
                chunk_id = int(entity["chunk_id"])
                chunk_scores[chunk_id] += 1.0 / (rrf_k + rank + 1)
                if chunk_id not in chunk_data:
                    chunk_data[chunk_id] = {
                        "chunk_id": chunk_id,
                        "kb_id": int(entity["kb_id"]),
                        "file_id": int(entity["file_id"]),
                        "text": entity["text"],
                        "vector_score": float(item.get("distance", 0.0)),
                    }

            # BM25 results contribution
            for rank, chunk in enumerate(bm25_chunks):
                chunk_id = chunk.id
                chunk_scores[chunk_id] += 1.0 / (rrf_k + rank + 1)
                if chunk_id not in chunk_data:
                    chunk_data[chunk_id] = {
                        "chunk_id": chunk_id,
                        "kb_id": chunk.kb_id,
                        "file_id": chunk.file_id,
                        "text": chunk.content,
                        "vector_score": 0.0,
                    }

            if not chunk_data:
                return []

            # Sort by RRF score
            sorted_chunks = sorted(chunk_scores.items(), key=lambda x: x[1], reverse=True)

            # Batch-fetch metadata from MySQL
            kb_id_list = list({chunk_data[cid]["kb_id"] for cid, _ in sorted_chunks if cid in chunk_data})
            file_id_list = list({chunk_data[cid]["file_id"] for cid, _ in sorted_chunks if cid in chunk_data})
            kb_map = {kb.id: kb for kb in kb_repo.get_kbs_by_ids(kb_id_list)}
            file_map = {f.id: f for f in file_repo.get_files_by_ids(file_id_list)}

            documents: list[Document] = []
            for chunk_id, rrf_score in sorted_chunks:
                data = chunk_data[chunk_id]
                kb_id = data["kb_id"]
                file_id = data["file_id"]
                kb = kb_map.get(kb_id)
                file = file_map.get(file_id)
                documents.append(
                    Document(
                        page_content=data["text"],
                        metadata={
                            "chunk_id": chunk_id,
                            "kb_id": kb_id,
                            "kb_name": getattr(kb, "name", f"KB {kb_id}"),
                            "file_id": file_id,
                            "file_name": file.file_name if file else "unknown",
                            "score": rrf_score,
                        },
                    )
                )

            # Rerank 精排
            if _enable_rerank and len(documents) > 1:
                texts = [doc.page_content for doc in documents]
                ranked = reranker_service.rerank(question, texts, top_k=_top_k)
                reranked_docs: list[Document] = []
                for orig_idx, score in ranked:
                    doc = documents[orig_idx]
                    doc.metadata["score"] = score
                    reranked_docs.append(doc)
                return reranked_docs

            return documents[:_top_k]

        return RunnableLambda(retrieve)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _doc_to_citation(doc: Document) -> CitationItem:
        m = doc.metadata
        return CitationItem(
            chunk_id=m["chunk_id"],
            kb_id=m["kb_id"],
            kb_name=m["kb_name"],
            file_id=m["file_id"],
            file_name=m["file_name"],
            score=m["score"],
            content=doc.page_content,
        )

    @staticmethod
    def _doc_to_context(doc: Document) -> str:
        m = doc.metadata
        return (
            f"知识库：{m['kb_name']}\n"
            f"文件：{m['file_name']}\n"
            f"内容：{doc.page_content}"
        )

    def _resolve_target_kb_ids(
        self, repo: KBRepo, kb_id: int | None, kb_ids: list[int]
    ) -> list[int]:
        normalized_ids = list(dict.fromkeys([*kb_ids, *([kb_id] if kb_id else [])]))
        if not normalized_ids:
            raise ValueError("At least one knowledge base must be selected")

        kbs = repo.get_kbs_by_ids(normalized_ids)
        if len(kbs) != len(set(normalized_ids)):
            found_ids = {kb.id for kb in kbs}
            missing_ids = [item for item in normalized_ids if item not in found_ids]
            raise ValueError(f"Knowledge bases not found: kb_ids={missing_ids}")
        return [kb.id for kb in kbs]



qa_service = QAService()
