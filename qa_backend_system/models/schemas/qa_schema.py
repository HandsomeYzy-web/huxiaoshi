from typing import List, Optional

from pydantic import BaseModel, Field


class QAAskRequest(BaseModel):
    kb_id: Optional[int] = Field(None, description="Single knowledge base ID")
    kb_ids: List[int] = Field(default_factory=list, description="Knowledge base IDs")
    question: str = Field(..., min_length=1, max_length=4000, description="User question")
    top_k: Optional[int] = Field(None, ge=1, le=20, description="Top K chunks to retrieve")


class CitationItem(BaseModel):
    chunk_id: int
    kb_id: int
    kb_name: str
    file_id: int
    file_name: str
    score: float
    content: str


class QAAskResponse(BaseModel):
    answer: str
    citations: List[CitationItem]
    retrieved_count: int
    model_used: Optional[str] = None


class ChatAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000, description="User question")
    top_k: Optional[int] = Field(None, ge=1, le=20, description="Top K chunks to retrieve")


class ChatAskResponse(BaseModel):
    answer: str
    citations: List[CitationItem]
    retrieved_count: int
    queried_kb_count: int
    queried_kb_ids: List[int]
    model_used: Optional[str] = None
