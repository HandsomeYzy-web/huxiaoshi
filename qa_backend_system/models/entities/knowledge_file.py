from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class KnowledgeFile(Base):
    __tablename__ = "knowledge_file"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="主键ID",
    )
    kb_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_base.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名称")
    file_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="文件扩展名")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件大小(字节)")
    md5: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="文件 MD5")
    minio_bucket: Mapped[str] = mapped_column(String(64), nullable=False, comment="MinIO 桶")
    minio_object_name: Mapped[str] = mapped_column(String(512), nullable=False, comment="MinIO 对象路径")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="0-待处理 1-解析中 2-完成 3-失败")
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息")
    custom_chunk_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="文件切分大小")
    custom_chunk_overlap: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="文件切分重叠")
    custom_separators: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="文件分隔符(JSON数组)")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase", back_populates="files")
