from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional
from datetime import datetime

class KBCreate(BaseModel):
    """创建知识库的请求体"""
    name: str = Field(..., max_length=128, description="知识库名称")
    description: Optional[str] = Field(None, max_length=512, description="知识库描述")
    default_chunk_size: int = Field(1000, ge=100, le=4000, description="默认切片大小")
    default_chunk_overlap: int = Field(200, ge=0, le=1000, description="默认切片重叠度")
    retrieval_top_k: int = Field(5, ge=1, le=50, description="检索返回条数")
    retrieval_score_threshold: float = Field(0.0, ge=0.0, le=1.0, description="检索最低相似度阈值")
    enable_rerank: bool = Field(False, description="是否对该知识库检索结果启用 Reranker")

    @model_validator(mode="after")
    def _check_overlap_lt_size(self):
        if self.default_chunk_overlap >= self.default_chunk_size:
            raise ValueError("切片重叠度(default_chunk_overlap)必须小于切片大小(default_chunk_size)")
        return self

class KBUpdate(BaseModel):
    """更新知识库的请求体 (字段全为可选)"""
    description: Optional[str] = Field(None, max_length=512)
    default_chunk_size: Optional[int] = Field(None, ge=100, le=4000)
    default_chunk_overlap: Optional[int] = Field(None, ge=0, le=1000)
    retrieval_top_k: Optional[int] = Field(None, ge=1, le=50)
    retrieval_score_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    enable_rerank: Optional[bool] = Field(None)

class KBResponse(BaseModel):
    """返回给前端的知识库信息"""
    id: int
    name: str
    description: Optional[str]
    default_chunk_size: int
    default_chunk_overlap: int
    retrieval_top_k: int
    retrieval_score_threshold: float
    enable_rerank: bool
    created_at: datetime
    updated_at: datetime

    # 允许从 SQLAlchemy ORM 模型直接转换
    model_config = ConfigDict(from_attributes=True)