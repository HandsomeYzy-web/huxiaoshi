from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional
from datetime import datetime

class FileStrategyUpdate(BaseModel):
    """用户单独指定某一个文件的切分策略请求体"""
    custom_chunk_size: int = Field(..., ge=100, le=4000, description="自定义切片大小")
    custom_chunk_overlap: int = Field(..., ge=0, le=1000, description="自定义切片重叠度")

    @model_validator(mode="after")
    def _check_overlap_lt_size(self):
        if self.custom_chunk_overlap >= self.custom_chunk_size:
            raise ValueError("切片重叠度必须小于切片大小")
        return self

class FileResponse(BaseModel):
    """返回给前端的文件信息"""
    id: int
    kb_id: int
    file_name: str
    file_type: str
    file_size: int
    status: int
    error_msg: Optional[str]
    custom_chunk_size: Optional[int]
    custom_chunk_overlap: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FilePageResponse(BaseModel):
    items: list[FileResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ChunkResponse(BaseModel):
    """返回给前端的文档分段信息"""
    id: int
    kb_id: int
    file_id: int
    chunk_index: int
    content: str
    char_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChunkPageResponse(BaseModel):
    """分页分段列表"""
    items: list[ChunkResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
