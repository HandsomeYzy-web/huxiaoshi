from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ModelConfig(Base):
    """模型配置表 — 存储 LLM、Embedding、Rerank 模型的连接信息"""
    __tablename__ = "model_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 模型类型: llm / embedding / rerank
    model_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="模型类型")
    # 模型供应商: openai / dashscope / ollama / zhipu / baichuan / moonshot / deepseek / local 等
    provider: Mapped[str] = mapped_column(String(64), nullable=False, comment="模型供应商")
    # 显示名称
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="模型显示名称")
    # 模型标识（API 调用用的 model name）
    model_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="模型标识/名称")
    # API Base URL
    api_base_url: Mapped[str] = mapped_column(String(512), nullable=False, comment="API Base URL")
    # API Key (加密存储)
    api_key: Mapped[str] = mapped_column(String(512), nullable=False, comment="API Key")
    # 是否为当前激活的模型（每种类型只有一个激活）
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否激活")
    # 额外参数 JSON（如 temperature, max_tokens, vector_dim 等）
    extra_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="额外参数(JSON)")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
