"""文件模块数据模型：包含文件上传、切分策略、分段预览、分页查询等接口模型。"""

from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List
from datetime import datetime

class FileRenameRequest(BaseModel):
    """文件重命名请求体"""
    new_name: str = Field(..., min_length=1, max_length=255, description="新文件名（含扩展名）")


class FileStrategyUpdate(BaseModel):
    """用户单独指定某一个文件的切分策略请求体"""
    custom_chunk_size: int = Field(..., ge=100, le=4000, description="自定义切片大小")
    custom_chunk_overlap: int = Field(..., ge=0, le=1000, description="自定义切片重叠度")
    custom_separators: Optional[List[str]] = Field(None, description="自定义分隔符列表")

    @model_validator(mode="after")
    def _check_overlap_lt_size(self):
        if self.custom_chunk_overlap >= self.custom_chunk_size:
            raise ValueError("切片重叠度必须小于切片大小")
        return self

class ChunkPreviewRequest(BaseModel):
    """预览切分结果的请求体"""
    file_id: int = Field(..., description="文件ID")
    chunk_size: int = Field(1000, ge=100, le=4000, description="切片大小")
    chunk_overlap: int = Field(200, ge=0, le=1000, description="切片重叠度")
    separators: Optional[List[str]] = Field(None, description="自定义分隔符列表")

    @model_validator(mode="after")
    def _check_overlap_lt_size(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("切片重叠度必须小于切片大小")
        return self

class ChunkPreviewItem(BaseModel):
    """预览切分结果的单个分段"""
    index: int
    content: str
    char_count: int

class ChunkPreviewResponse(BaseModel):
    """预览切分结果"""
    total_chunks: int
    chunks: List[ChunkPreviewItem]
    total_chars: int

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
    custom_separators: Optional[str] = None
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
