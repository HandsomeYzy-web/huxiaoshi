from typing import List, Optional

from pydantic import BaseModel, Field


class QAAskRequest(BaseModel):
    kb_id: int = Field(..., description="Knowledge base ID")
    question: str = Field(..., min_length=1, max_length=4000, description="User question")
    top_k: int = Field(5, ge=1, le=20, description="Top K chunks to retrieve")


class CitationItem(BaseModel):
    chunk_id: int
    file_id: int
    file_name: str
    score: float
    content: str


class QAAskResponse(BaseModel):
    answer: str
    citations: List[CitationItem]
    retrieved_count: int
    model_used: Optional[str] = None
