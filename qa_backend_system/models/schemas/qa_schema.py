"""问答模块数据模型：包含知识库问答、检索测试、跨库聊天等接口的请求/响应模型。"""

from typing import List, Optional

from pydantic import BaseModel, Field


class QAAskRequest(BaseModel):
    """知识库问答请求：指定知识库 ID 和问题进行问答或检索测试。"""
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
