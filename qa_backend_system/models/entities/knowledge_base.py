from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base  # 引入基类


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="所属用户ID")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="知识库名称")
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="知识库描述")
    default_chunk_size: Mapped[int] = mapped_column(Integer, default=1000, nullable=False, comment="默认文本块大小")
    default_chunk_overlap: Mapped[int] = mapped_column(Integer, default=200, nullable=False, comment="默认重叠大小")
    retrieval_top_k: Mapped[int] = mapped_column(Integer, default=5, nullable=False, comment="检索返回条数")
    retrieval_score_threshold: Mapped[float] = mapped_column(nullable=False, default=0.0, comment="检索最低相似度阈值")
    enable_rerank: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否启用 Reranker")

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="软删除标记")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False,
                                                 comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(),
                                                 nullable=False, comment="更新时间")

    # 注意：关联的类名必须使用字符串，避免与 knowledge_file.py 产生循环导入
    files: Mapped[List["KnowledgeFile"]] = relationship("KnowledgeFile", back_populates="knowledge_base",
                                                        cascade="all, delete-orphan")