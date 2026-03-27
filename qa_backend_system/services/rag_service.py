import os
import tempfile
import uuid

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session
from unstructured.documents.elements import Image, Table
from unstructured.partition.auto import partition

from core.config import settings
from core.logger import logger
from models.entities import DocumentChunk, KnowledgeBase, KnowledgeFile
from repositories.meta_repo import MetaRepo
from repositories.milvus_repo import milvus_repo
from repositories.minio_repo import minio_repo
from services.custom_e5_embeddings import CustomE5Embeddings


class RAGService:
    """Document processing and vector indexing pipeline."""

    def __init__(self):
        self.embeddings = CustomE5Embeddings(
            api_base=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
            model=settings.EMBEDDING_MODEL,
        )

    def process_and_embed_file(self, db: Session, file_entity: KnowledgeFile, kb_entity: KnowledgeBase):
        logger.info(f"Start processing document: {file_entity.file_name}")

        chunk_size = file_entity.custom_chunk_size or kb_entity.default_chunk_size
        chunk_overlap = file_entity.custom_chunk_overlap or kb_entity.default_chunk_overlap

        full_text = self._extract_text(file_entity, kb_entity)
        chunks = self._split_text(full_text, chunk_size, chunk_overlap, file_entity)
        if not chunks:
            logger.warning(f"No chunks produced for file: {file_entity.file_name}")
            return

        repo = MetaRepo(db)
        chunk_entities = [
            DocumentChunk(
                kb_id=file_entity.kb_id,
                file_id=file_entity.id,
                chunk_index=index,
                content=chunk.page_content,
                char_count=len(chunk.page_content),
            )
            for index, chunk in enumerate(chunks)
        ]
        saved_chunks = repo.bulk_create_chunks(chunk_entities)

        vectors = self.embeddings.embed_documents([chunk.content for chunk in saved_chunks])
        vector_rows = [
            {
                "chunk_id": chunk.id,
                "kb_id": chunk.kb_id,
                "file_id": chunk.file_id,
                "text": chunk.content,
                "embedding": vector,
            }
            for chunk, vector in zip(saved_chunks, vectors)
        ]
        milvus_repo.insert_chunks(vector_rows)
        logger.info(f"Indexed {len(saved_chunks)} chunks for file: {file_entity.file_name}")

    def _extract_text(self, file_entity: KnowledgeFile, kb_entity: KnowledgeBase) -> str:
        with tempfile.TemporaryDirectory() as temp_dir:
            local_file_path = os.path.join(temp_dir, file_entity.file_name)
            response = minio_repo.get_file_stream(file_entity.minio_object_name)
            with open(local_file_path, "wb") as file_obj:
                file_obj.write(response.read())
            response.close()
            response.release_conn()

            elements = partition(
                filename=local_file_path,
                extract_image_block_types=["Image", "Table"],
                extract_image_block_output_dir=temp_dir,
            )

            full_text = ""
            for element in elements:
                if (
                    isinstance(element, (Image, Table))
                    and hasattr(element.metadata, "image_path")
                    and element.metadata.image_path
                ):
                    img_local_path = element.metadata.image_path
                    if os.path.exists(img_local_path):
                        img_ext = os.path.splitext(img_local_path)[1]
                        img_object_name = f"kb_{kb_entity.id}/images/{uuid.uuid4().hex}{img_ext}"

                        with open(img_local_path, "rb") as img_file:
                            img_bytes = img_file.read()
                            minio_repo.upload_file_bytes(
                                img_object_name,
                                img_bytes,
                                content_type=f"image/{img_ext.strip('.')}",
                            )

                        img_url = minio_repo.get_presigned_url(img_object_name, expires_hours=24 * 7)
                        full_text += f"\n\n![文档插图]({img_url})\n\n"
                else:
                    full_text += str(element) + "\n\n"
            return full_text

    def _split_text(
        self,
        full_text: str,
        chunk_size: int,
        chunk_overlap: int,
        file_entity: KnowledgeFile,
    ) -> list[Document]:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "，", " ", ""],
        )
        base_doc = Document(
            page_content=full_text,
            metadata={"kb_id": file_entity.kb_id, "file_id": file_entity.id},
        )
        chunks = text_splitter.split_documents([base_doc])
        logger.info(f"Split document into {len(chunks)} chunks: {file_entity.file_name}")
        return chunks


rag_service = RAGService()
