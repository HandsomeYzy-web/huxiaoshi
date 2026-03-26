from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class KBCreate(BaseModel):
    """创建知识库的请求体"""
    name: str = Field(..., max_length=128, description="知识库名称")
    description: Optional[str] = Field(None, max_length=512, description="知识库描述")
    default_chunk_size: int = Field(1000, ge=100, le=4000, description="默认切片大小")
    default_chunk_overlap: int = Field(200, ge=0, le=1000, description="默认切片重叠度")

class KBUpdate(BaseModel):
    """更新知识库的请求体 (字段全为可选)"""
    description: Optional[str] = Field(None, max_length=512)
    default_chunk_size: Optional[int] = Field(None, ge=100, le=4000)
    default_chunk_overlap: Optional[int] = Field(None, ge=0, le=1000)

class KBResponse(BaseModel):
    """返回给前端的知识库信息"""
    id: int
    name: str
    description: Optional[str]
    default_chunk_size: int
    default_chunk_overlap: int
    created_at: datetime
    updated_at: datetime

    # 允许从 SQLAlchemy ORM 模型直接转换
    model_config = ConfigDict(from_attributes=True)