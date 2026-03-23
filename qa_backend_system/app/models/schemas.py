from pydantic import BaseModel
from typing import Optional, Any, Generic, TypeVar

# 定义泛型变量，代表 data 字段可以是任何类型
T = TypeVar("T")

class BaseResponse(BaseModel, Generic[T]):
    code: int = 200
    msg: str = "success"
    data: Optional[T] = None

# 为了方便，封装两个快速返回的方法
def success_resp(data: Any = None, msg: str = "success") -> BaseResponse:
    return BaseResponse(code=200, msg=msg, data=data)

def error_resp(code: int = 400, msg: str = "error") -> BaseResponse:
    return BaseResponse(code=code, msg=msg, data=None)

# ---------------- 下面是你之前写的请求模型 ----------------
class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None

class KBCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    embedding_model: str  # 例如: "text-embedding-v1"

class KBModelUpdateRequest(BaseModel):
    new_embedding_model: str

class PreviewChunkRequest(BaseModel):
    chunk_size: int = 500
    chunk_overlap: int = 50
    # 前端以 FormData 传文件，所以切分规则我们后续通过 Form 接收，这里主要做个结构参考