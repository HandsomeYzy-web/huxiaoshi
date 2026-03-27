from sqlalchemy.orm import Session

from models.schemas.qa_schema import CitationItem, QAAskRequest, QAAskResponse
from repositories.meta_repo import MetaRepo
from repositories.milvus_repo import milvus_repo
from services.custom_e5_embeddings import CustomE5Embeddings
from services.llm_service import llm_service
from core.config import settings


class QAService:
    def __init__(self):
        self.embeddings = CustomE5Embeddings(
            api_base=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
            model=settings.EMBEDDING_MODEL,
        )

    def ask(self, db: Session, request: QAAskRequest) -> QAAskResponse:
        repo = MetaRepo(db)
        kb_entity = repo.get_kb_by_id(request.kb_id)
        if not kb_entity:
            raise ValueError(f"Knowledge base not found: kb_id={request.kb_id}")

        query_vector = self.embeddings.embed_query(request.question)
        results = milvus_repo.search_chunks(request.kb_id, query_vector, top_k=request.top_k)
        file_map = {file.id: file for file in repo.get_files_by_ids(item["entity"]["file_id"] for item in results)}

        citations = []
        contexts = []
        for item in results:
            entity = item["entity"]
            score = float(item.get("distance", 0.0))
            file_entity = file_map.get(entity["file_id"])
            citation = CitationItem(
                chunk_id=int(entity["chunk_id"]),
                file_id=int(entity["file_id"]),
                file_name=file_entity.file_name if file_entity else "unknown",
                score=score,
                content=entity["text"],
            )
            citations.append(citation)
            contexts.append(entity["text"])

        answer, model_used = llm_service.generate_answer(request.question, contexts)
        return QAAskResponse(
            answer=answer,
            citations=citations,
            retrieved_count=len(citations),
            model_used=model_used,
        )


qa_service = QAService()
