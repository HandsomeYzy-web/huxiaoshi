"""
QA 服务层 — 检索增强生成（RAG）管道。

使用向量查询（Elasticsearch）进行语义检索，可选 Rerank 精排后返回最终结果集。

The retrieval step is encapsulated as a LangChain RunnableLambda so it can be
composed into any LCEL chain.
"""
from __future__ import annotations


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
from repositories.elasticsearch_repo import es_repo
from services import embeddings
from services.kb_scope import filter_document_kbs, get_document_kb_ids, is_reserved_kb
from services.llm_service import llm_service
from services.reranker_service import reranker_service


class QAService:
    def ask(self, db: Session, request: QAAskRequest, user_id: int) -> QAAskResponse:
        repo = KBRepo(db)
        target_kb_ids = self._resolve_target_kb_ids(db, repo, request.kb_id, request.kb_ids, user_id)
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

    def retrieve(self, db: Session, request: QAAskRequest, user_id: int) -> QAAskResponse:
        repo = KBRepo(db)
        target_kb_ids = self._resolve_target_kb_ids(db, repo, request.kb_id, request.kb_ids, user_id)
        top_k = request.top_k or settings.DEFAULT_RETRIEVAL_TOP_K

        docs = self._make_retriever(db, target_kb_ids, top_k).invoke(request.question)
        citations = [self._doc_to_citation(doc) for doc in docs]
        return QAAskResponse(
            answer="",
            citations=citations,
            retrieved_count=len(citations),
            model_used=None,
        )

    def chat(self, db: Session, request: ChatAskRequest, user_id: int) -> ChatAskResponse:
        # 知识库隔离：文档问答不检索 text2SQL 专用的 table_desc / few-shot 保留库。
        accessible_ids = get_document_kb_ids(db)
        if not accessible_ids:
            raise ValueError("No knowledge bases available")

        top_k = request.top_k or settings.DEFAULT_RETRIEVAL_TOP_K

        docs = self._make_retriever(db, accessible_ids, top_k).invoke(request.question)
        citations = [self._doc_to_citation(doc) for doc in docs]
        contexts = [self._doc_to_context(doc) for doc in docs]

        answer, model_used = llm_service.generate_answer(request.question, contexts)
        return ChatAskResponse(
            answer=answer,
            citations=citations,
            retrieved_count=len(citations),
            queried_kb_count=len(accessible_ids),
            queried_kb_ids=accessible_ids,
            model_used=model_used,
        )

    def retrieve_for_chat(
        self, db: Session, question: str, user_id: int, top_k: int | None = None
    ) -> dict:
        """仅检索，不生成答案。返回 {"citations": list[CitationItem], "contexts": list[str]}"""
        # 知识库隔离：排除 text2SQL 专用的 table_desc / few-shot 保留库。
        accessible_ids = get_document_kb_ids(db)
        if not accessible_ids:
            return {"citations": [], "contexts": []}

        effective_top_k = top_k or settings.DEFAULT_RETRIEVAL_TOP_K
        docs = self._make_retriever(db, accessible_ids, effective_top_k).invoke(question)
        citations = [self._doc_to_citation(doc) for doc in docs]
        contexts = [self._doc_to_context(doc) for doc in docs]
        return {"citations": citations, "contexts": contexts}

    def retrieve_for_chat_with_context(
        self,
        db: Session,
        question: str,
        rewritten_question: str,
        user_id: int,
        top_k: int | None = None,
    ) -> dict:
        """使用原始 query 和改写 query 分别检索知识库，合并去重后返回最终结果。
        返回 {"citations": list[CitationItem], "contexts": list[str]}
        """
        # 知识库隔离：排除 text2SQL 专用的 table_desc / few-shot 保留库。
        accessible_ids = get_document_kb_ids(db)
        if not accessible_ids:
            return {"citations": [], "contexts": []}

        effective_top_k = top_k or settings.DEFAULT_RETRIEVAL_TOP_K
        retriever = self._make_retriever(db, accessible_ids, effective_top_k)

        original_docs = retriever.invoke(question)
        rewritten_docs = (
            retriever.invoke(rewritten_question)
            if rewritten_question and rewritten_question != question
            else []
        )

        # 按 chunk_id 去重，原始查询结果优先
        seen: dict[int, Document] = {}
        for doc in original_docs + rewritten_docs:
            chunk_id = doc.metadata.get("chunk_id")
            if chunk_id is not None and chunk_id not in seen:
                seen[chunk_id] = doc

        final_docs = list(seen.values())[:effective_top_k]
        citations = [self._doc_to_citation(doc) for doc in final_docs]
        contexts = [self._doc_to_context(doc) for doc in final_docs]
        return {"citations": citations, "contexts": contexts}

    # ------------------------------------------------------------------
    # LangChain retriever factory (pure vector RAG)
    # ------------------------------------------------------------------

    def _make_retriever(
        self,
        db: Session,
        kb_ids: list[int] | None,
        top_k: int,
        score_threshold: float = 0.0,
    ) -> RunnableLambda:
        """
        Returns a LangChain RunnableLambda that performs pure vector retrieval:
        1. Vector search via Elasticsearch (semantic similarity)
        2. Optional reranking

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
            query_vector = embeddings.get_embeddings().embed_query(question)
            kb_repo = KBRepo(db)
            file_repo = FileRepo(db)

            # 启用 rerank 时先多取候选集
            fetch_k = _top_k * 3 if _enable_rerank else _top_k

            # ── 1. Vector search (Elasticsearch) ──────────────────
            if kb_ids and len(kb_ids) == 1:
                vector_results = es_repo.search_chunks(kb_ids[0], query_vector, top_k=fetch_k)
            elif kb_ids:
                vector_results = es_repo.search_chunks_across_kbs(kb_ids, query_vector, top_k=fetch_k)
            else:
                # 未指定 kb_ids 时检索全部文档知识库（隔离规则已排除 text2SQL 保留库）
                all_kb_ids = [kb.id for kb in filter_document_kbs(kb_repo.get_all_kbs())]
                if not all_kb_ids:
                    vector_results = []
                else:
                    vector_results = es_repo.search_chunks_across_kbs(all_kb_ids, query_vector, top_k=fetch_k)

            # Apply score threshold filter
            if _score_threshold > 0.0:
                vector_results = [r for r in vector_results if float(r.get("distance", 0.0)) >= _score_threshold]

            if not vector_results:
                return []

            # ── 2. Build Document list from vector results ────────
            kb_id_list = list({int(r["entity"]["kb_id"]) for r in vector_results})
            file_id_list = list({int(r["entity"]["file_id"]) for r in vector_results})
            kb_map = {kb.id: kb for kb in kb_repo.get_kbs_by_ids(kb_id_list)}
            file_map = {f.id: f for f in file_repo.get_files_by_ids(file_id_list)}

            documents: list[Document] = []
            for item in vector_results:
                entity = item["entity"]
                chunk_id = int(entity["chunk_id"])
                kb_id = int(entity["kb_id"])
                file_id = int(entity["file_id"])
                kb = kb_map.get(kb_id)
                file = file_map.get(file_id)
                documents.append(
                    Document(
                        page_content=entity["text"],
                        metadata={
                            "chunk_id": chunk_id,
                            "kb_id": kb_id,
                            "kb_name": getattr(kb, "name", f"KB {kb_id}"),
                            "file_id": file_id,
                            "file_name": file.file_name if file else "unknown",
                            "score": float(item.get("distance", 0.0)),
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
        self, db: Session, repo: KBRepo, kb_id: int | None, kb_ids: list[int], user_id: int
    ) -> list[int]:
        from core.exceptions import BusinessError, ResourceNotFoundError

        normalized_ids = list(dict.fromkeys([*kb_ids, *([kb_id] if kb_id else [])]))
        if not normalized_ids:
            raise ValueError("At least one knowledge base must be selected")

        kbs = repo.get_kbs_by_ids(normalized_ids)
        if len(kbs) != len(set(normalized_ids)):
            found_ids = {kb.id for kb in kbs}
            missing_ids = [item for item in normalized_ids if item not in found_ids]
            raise ResourceNotFoundError(f"Knowledge bases not found: kb_ids={missing_ids}")

        # 知识库隔离：table_desc / few-shot 为 text2SQL 专用保留库，文档问答不可指定。
        reserved_names = [str(kb.name) for kb in kbs if is_reserved_kb(kb)]
        if reserved_names:
            raise BusinessError(
                f"知识库 {reserved_names} 为 text2SQL 专用保留库，不可用于文档问答"
            )

        return [kb.id for kb in kbs]



qa_service = QAService()
