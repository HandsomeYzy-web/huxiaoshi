from sqlalchemy.orm import Session

from core.config import settings
from models.schemas.qa_schema import (
    ChatAskRequest,
    ChatAskResponse,
    CitationItem,
    QAAskRequest,
    QAAskResponse,
)
from repositories.meta_repo import MetaRepo
from repositories.milvus_repo import milvus_repo
from services.custom_e5_embeddings import CustomE5Embeddings
from services.llm_service import llm_service


class QAService:
    def __init__(self):
        self.embeddings = CustomE5Embeddings(
            api_base=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
            model=settings.EMBEDDING_MODEL,
        )

    def ask(self, db: Session, request: QAAskRequest) -> QAAskResponse:
        citations, contexts = self._retrieve(db, request)
        answer, model_used = llm_service.generate_answer(request.question, contexts)
        return QAAskResponse(
            answer=answer,
            citations=citations,
            retrieved_count=len(citations),
            model_used=model_used,
        )

    def retrieve(self, db: Session, request: QAAskRequest) -> QAAskResponse:
        citations, _ = self._retrieve(db, request)
        return QAAskResponse(
            answer="",
            citations=citations,
            retrieved_count=len(citations),
            model_used=None,
        )

    def _retrieve(self, db: Session, request: QAAskRequest) -> tuple[list[CitationItem], list[str]]:
        repo = MetaRepo(db)
        target_kb_ids = self._resolve_target_kb_ids(repo, request.kb_id, request.kb_ids)
        kb_map = {kb.id: kb for kb in repo.get_kbs_by_ids(target_kb_ids)}
        top_k = request.top_k or settings.DEFAULT_RETRIEVAL_TOP_K

        query_vector = self.embeddings.embed_query(request.question)
        if len(target_kb_ids) == 1:
            results = milvus_repo.search_chunks(target_kb_ids[0], query_vector, top_k=top_k)
        else:
            results = [
                item
                for item in milvus_repo.search_chunks_across_kbs(query_vector, top_k=top_k * 3)
                if int(item["entity"]["kb_id"]) in kb_map
            ][:top_k]

        return self._build_citations(repo, results, kb_map)

    def chat(self, db: Session, request: ChatAskRequest) -> ChatAskResponse:
        repo = MetaRepo(db)
        knowledge_bases = repo.get_all_kbs()
        if not knowledge_bases:
            raise ValueError("No knowledge bases available")

        kb_map = {kb.id: kb for kb in knowledge_bases}
        top_k = request.top_k or settings.DEFAULT_RETRIEVAL_TOP_K
        query_vector = self.embeddings.embed_query(request.question)
        results = milvus_repo.search_chunks_across_kbs(query_vector, top_k=top_k)
        citations, contexts = self._build_citations(repo, results, kb_map)

        answer, model_used = llm_service.generate_answer(request.question, contexts)
        return ChatAskResponse(
            answer=answer,
            citations=citations,
            retrieved_count=len(citations),
            queried_kb_count=len(kb_map),
            queried_kb_ids=list(kb_map.keys()),
            model_used=model_used,
        )

    def _resolve_target_kb_ids(self, repo: MetaRepo, kb_id: int | None, kb_ids: list[int]) -> list[int]:
        normalized_ids = list(dict.fromkeys([*kb_ids, *([kb_id] if kb_id else [])]))
        if not normalized_ids:
            raise ValueError("At least one knowledge base must be selected")

        kbs = repo.get_kbs_by_ids(normalized_ids)
        if len(kbs) != len(set(normalized_ids)):
            found_ids = {kb.id for kb in kbs}
            missing_ids = [item for item in normalized_ids if item not in found_ids]
            raise ValueError(f"Knowledge bases not found: kb_ids={missing_ids}")
        return [kb.id for kb in kbs]

    def _build_citations(
        self,
        repo: MetaRepo,
        results: list[dict],
        kb_map: dict[int, object],
    ) -> tuple[list[CitationItem], list[str]]:
        file_map = {
            file.id: file for file in repo.get_files_by_ids(item["entity"]["file_id"] for item in results)
        }

        citations: list[CitationItem] = []
        contexts: list[str] = []
        for item in results:
            entity = item["entity"]
            kb_id = int(entity["kb_id"])
            file_id = int(entity["file_id"])
            kb_entity = kb_map.get(kb_id)
            file_entity = file_map.get(file_id)
            content = entity["text"]

            citations.append(
                CitationItem(
                    chunk_id=int(entity["chunk_id"]),
                    kb_id=kb_id,
                    kb_name=getattr(kb_entity, "name", f"KB {kb_id}"),
                    file_id=file_id,
                    file_name=file_entity.file_name if file_entity else "unknown",
                    score=float(item.get("distance", 0.0)),
                    content=content,
                )
            )
            contexts.append(
                f"知识库：{getattr(kb_entity, 'name', f'KB {kb_id}')}\n"
                f"文件：{file_entity.file_name if file_entity else 'unknown'}\n"
                f"内容：{content}"
            )
        return citations, contexts


qa_service = QAService()
