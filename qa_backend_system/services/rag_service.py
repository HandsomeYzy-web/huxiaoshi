import os
import tempfile
import uuid
from typing import List, Optional
from unstructured.partition.auto import partition
from unstructured.documents.elements import Image, Table

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_milvus import Milvus

from core.config import settings
from core.logger import logger
from models.entities import KnowledgeFile, KnowledgeBase
from repositories.minio_repo import minio_repo


class RAGService:
    """RAG 核心引擎：处理多模态文档解析、分块与向量化"""

    def __init__(self):
        # 初始化 Embedding 模型是安全的，它不需要连接数据库
        self.embeddings = DashScopeEmbeddings(
            model="text-embedding-v1",
            dashscope_api_key=settings.DASHSCOPE_API_KEY
        )
        # 🟢 关键修改 1：不在这里直接实例化 Milvus，设为 None
        self._vector_store: Optional[Milvus] = None

    @property
    def vector_store(self) -> Milvus:
        """
        🟢 关键修改 2：使用懒加载属性 (Lazy Property)
        只有在第一次真正用到 vector_store 时，才会执行初始化并连接。
        此时 main.py 的 lifespan 早就执行完毕，底层的 pymilvus.connections 已经建立好了。
        """
        if self._vector_store is None:
            self._vector_store = Milvus(
                embedding_function=self.embeddings,
                connection_args={"host": settings.MILVUS_HOST, "port": settings.MILVUS_PORT},
                collection_name="qa_knowledge_collection",
                auto_id=True,
                drop_old=False
            )
        return self._vector_store

    def process_and_embed_file(self, file_entity: KnowledgeFile, kb_entity: KnowledgeBase):
        """核心方法：处理单个文件并存入 Milvus"""
        logger.info(f"开始解析文档: {file_entity.file_name}")

        chunk_size = file_entity.custom_chunk_size or kb_entity.default_chunk_size
        chunk_overlap = file_entity.custom_chunk_overlap or kb_entity.default_chunk_overlap

        with tempfile.TemporaryDirectory() as temp_dir:
            local_file_path = os.path.join(temp_dir, file_entity.file_name)
            response = minio_repo.get_file_stream(file_entity.minio_object_name)
            with open(local_file_path, "wb") as f:
                f.write(response.read())
            response.close()
            response.release_conn()

            elements = partition(
                filename=local_file_path,
                extract_image_block_types=["Image", "Table"],
                extract_image_block_output_dir=temp_dir
            )

            full_text = ""
            for el in elements:
                if isinstance(el, (Image, Table)) and hasattr(el.metadata, 'image_path') and el.metadata.image_path:
                    img_local_path = el.metadata.image_path
                    if os.path.exists(img_local_path):
                        img_ext = os.path.splitext(img_local_path)[1]
                        img_object_name = f"kb_{kb_entity.id}/images/{uuid.uuid4().hex}{img_ext}"

                        with open(img_local_path, "rb") as img_f:
                            img_bytes = img_f.read()
                            minio_repo.upload_file_bytes(img_object_name, img_bytes,
                                                         content_type=f"image/{img_ext.strip('.')}")

                        img_url = minio_repo.get_presigned_url(img_object_name, expires_hours=24 * 7)
                        full_text += f"\n\n![文档插图]({img_url})\n\n"
                else:
                    full_text += str(el) + "\n\n"

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", "。", "！", "？", " ", ""]
            )

            base_doc = Document(
                page_content=full_text,
                metadata={"kb_id": file_entity.kb_id, "file_id": file_entity.id}
            )

            chunks = text_splitter.split_documents([base_doc])
            logger.info(f"文档切分完成: {file_entity.file_name}, 共 {len(chunks)} 个 Chunk")

            if chunks:
                # 🟢 关键修改 3：调用 self.vector_store 时会触发上面的懒加载属性
                self.vector_store.add_documents(chunks)
                logger.info(f"文档向量化并写入 Milvus 成功: {file_entity.file_name}")
            else:
                logger.warning(f"文档解析为空或切分失败: {file_entity.file_name}")


rag_service = RAGService()