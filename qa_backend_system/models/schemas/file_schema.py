from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class FileStrategyUpdate(BaseModel):
    """用户单独指定某一个文件的切分策略请求体"""
    custom_chunk_size: int = Field(..., ge=100, le=4000, description="自定义切片大小")
    custom_chunk_overlap: int = Field(..., ge=0, le=1000, description="自定义切片重叠度")

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