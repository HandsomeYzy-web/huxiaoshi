from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.schemas.qa_schema import CitationItem


class ChatSessionCreateRequest(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=255)


class ChatSessionRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class ChatSessionSummary(BaseModel):
    id: int
    title: str
    updated_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatMessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    model_used: str | None = None
    retrieved_count: int = 0
    citations: list[CitationItem] = Field(default_factory=list)
    # ── 三链路扩展 ───────────────────────────────────────────────
    intent: str | None = None  # casual_chat / data_query / doc_search
    generated_sql: str | None = None
    sql_result_json: str | None = None
    created_at: datetime


class ChatDocumentItem(BaseModel):
    kb_id: int
    kb_name: str
    file_id: int
    file_name: str


class ChatSessionDetail(BaseModel):
    session: ChatSessionSummary
    messages: list[ChatMessageResponse]
    involved_documents: list[ChatDocumentItem]


class ChatMessageCreateRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)


class ChatMessageCreateResponse(BaseModel):
    session: ChatSessionSummary
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
    involved_documents: list[ChatDocumentItem]
