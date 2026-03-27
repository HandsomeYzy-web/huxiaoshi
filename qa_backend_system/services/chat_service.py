import json

from sqlalchemy.orm import Session

from core.config import settings
from models.entities import ChatMessage, ChatSession
from models.schemas.chat_schema import (
    ChatDocumentItem,
    ChatMessageCreateRequest,
    ChatMessageCreateResponse,
    ChatMessageResponse,
    ChatSessionCreateRequest,
    ChatSessionDetail,
    ChatSessionSummary,
)
from models.schemas.qa_schema import ChatAskRequest, CitationItem
from repositories.meta_repo import MetaRepo
from services.qa_service import qa_service


class ChatService:
    DEFAULT_USER_ID = 1

    def list_sessions(self, db: Session) -> list[ChatSessionSummary]:
        repo = MetaRepo(db)
        sessions = repo.list_chat_sessions(self.DEFAULT_USER_ID)
        return [ChatSessionSummary.model_validate(session) for session in sessions]

    def create_session(self, db: Session, request: ChatSessionCreateRequest) -> ChatSessionSummary:
        repo = MetaRepo(db)
        session = repo.create_chat_session(ChatSession(user_id=self.DEFAULT_USER_ID, title=request.title.strip()))
        return ChatSessionSummary.model_validate(session)

    def get_session_detail(self, db: Session, session_id: int) -> ChatSessionDetail:
        repo = MetaRepo(db)
        session = repo.get_chat_session(session_id, self.DEFAULT_USER_ID)
        if not session:
            raise ValueError(f"Chat session not found: session_id={session_id}")
        messages = repo.list_chat_messages(session_id)
        return ChatSessionDetail(
            session=ChatSessionSummary.model_validate(session),
            messages=[self._to_message_response(message) for message in messages],
            involved_documents=self._collect_documents(messages),
        )

    def append_message(self, db: Session, session_id: int, request: ChatMessageCreateRequest) -> ChatMessageCreateResponse:
        repo = MetaRepo(db)
        session = repo.get_chat_session(session_id, self.DEFAULT_USER_ID)
        if not session:
            raise ValueError(f"Chat session not found: session_id={session_id}")

        question = request.question.strip()
        user_message = repo.create_chat_message(
            ChatMessage(session_id=session.id, role="user", content=question, retrieved_count=0)
        )

        qa_result = qa_service.chat(
            db,
            request=ChatAskRequest(question=question, top_k=settings.DEFAULT_RETRIEVAL_TOP_K),
        )
        assistant_message = repo.create_chat_message(
            ChatMessage(
                session_id=session.id,
                role="assistant",
                content=qa_result.answer,
                model_used=qa_result.model_used,
                retrieved_count=qa_result.retrieved_count,
                citations_json=json.dumps([item.model_dump() for item in qa_result.citations], ensure_ascii=False),
            )
        )

        if session.title == "新对话":
            repo.update_chat_session_title(session.id, self._build_title(question))
        repo.touch_chat_session(session.id)
        refreshed_session = repo.get_chat_session(session.id, self.DEFAULT_USER_ID)
        messages = repo.list_chat_messages(session.id)
        return ChatMessageCreateResponse(
            session=ChatSessionSummary.model_validate(refreshed_session),
            user_message=self._to_message_response(user_message),
            assistant_message=self._to_message_response(assistant_message),
            involved_documents=self._collect_documents(messages),
        )

    def _to_message_response(self, message: ChatMessage) -> ChatMessageResponse:
        citations = []
        if message.citations_json:
            citations = [CitationItem.model_validate(item) for item in json.loads(message.citations_json)]
        return ChatMessageResponse(
            id=message.id,
            session_id=message.session_id,
            role=message.role,
            content=message.content,
            model_used=message.model_used,
            retrieved_count=message.retrieved_count,
            citations=citations,
            created_at=message.created_at,
        )

    def _collect_documents(self, messages: list[ChatMessage]) -> list[ChatDocumentItem]:
        seen: set[tuple[int, int]] = set()
        documents: list[ChatDocumentItem] = []
        for message in messages:
            if not message.citations_json:
                continue
            for item in json.loads(message.citations_json):
                key = (int(item["kb_id"]), int(item["file_id"]))
                if key in seen:
                    continue
                seen.add(key)
                documents.append(
                    ChatDocumentItem(
                        kb_id=int(item["kb_id"]),
                        kb_name=item["kb_name"],
                        file_id=int(item["file_id"]),
                        file_name=item["file_name"],
                    )
                )
        return documents

    def _build_title(self, question: str) -> str:
        return question[:24] + ("..." if len(question) > 24 else "")


chat_service = ChatService()
