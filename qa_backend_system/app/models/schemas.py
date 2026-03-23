from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    query: str  # 用户输入的问题
    session_id: Optional[str] = None  # 以后用来关联 MySQL 里的历史对话记录