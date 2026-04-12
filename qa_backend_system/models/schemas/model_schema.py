"""模型配置模块数据模型：包含模型配置的 CRUD、激活、供应商信息等接口模型。"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict


# ── 模型供应商常量 ─────────────────────────────────────────────
SUPPORTED_PROVIDERS = [
    "openai", "dashscope", "zhipu", "baichuan", "moonshot",
    "deepseek", "ollama", "azure_openai", "anthropic",
    "cohere", "jina", "local", "custom",
]

SUPPORTED_MODEL_TYPES = ["llm", "embedding", "rerank"]


class ModelConfigCreate(BaseModel):
    """创建模型配置"""
    model_type: str = Field(..., description="模型类型: llm / embedding / rerank")
    provider: str = Field(..., max_length=64, description="模型供应商")
    name: str = Field(..., max_length=128, description="模型显示名称")
    model_name: str = Field(..., max_length=256, description="模型标识")
    api_base_url: str = Field(..., max_length=512, description="API Base URL")
    api_key: str = Field(..., max_length=512, description="API Key")
    is_active: bool = Field(False, description="是否激活")
    extra_params: Optional[str] = Field(None, description="额外参数(JSON)")


class ModelConfigUpdate(BaseModel):
    """更新模型配置"""
    name: Optional[str] = Field(None, max_length=128)
    model_name: Optional[str] = Field(None, max_length=256)
    api_base_url: Optional[str] = Field(None, max_length=512)
    api_key: Optional[str] = Field(None, max_length=512)
    is_active: Optional[bool] = None
    extra_params: Optional[str] = None


class ModelConfigResponse(BaseModel):
    """模型配置响应"""
    id: int
    model_type: str
    provider: str
    name: str
    model_name: str
    api_base_url: str
    api_key_masked: str = Field(description="脱敏后的 API Key")
    is_active: bool
    extra_params: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ModelProviderInfo(BaseModel):
    """模型供应商信息"""
    provider: str
    display_name: str
    supported_types: List[str]


class ModelActivateRequest(BaseModel):
    """激活模型请求"""
    model_id: int = Field(..., description="要激活的模型配置ID")


class ModelActivateResponse(BaseModel):
    """激活模型响应 — 可携带警告信息"""
    config: ModelConfigResponse
    warning: Optional[str] = Field(None, description="操作警告（如 embedding 切换需重建知识库）")
    needs_rebuild: bool = Field(False, description="是否需要重建所有知识库向量")
