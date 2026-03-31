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
from repositories.file_repo import FileRepo
from repositories.milvus_repo import milvus_repo
from repositories.minio_repo import minio_repo
from services.embeddings import get_embeddings

# ── Image file extensions handled as pure images (OCR/description) ────
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "tiff", "webp", "gif"}

# ── Mapping of file types to unstructured partition strategies ────────
# "auto" lets unstructured choose; "ocr_only" forces OCR for scanned PDFs.
_STRATEGY_MAP: dict[str, str] = {
    "pdf": "hi_res",
    "png": "ocr_only",
    "jpg": "ocr_only",
    "jpeg": "ocr_only",
    "bmp": "ocr_only",
    "tiff": "ocr_only",
    "webp": "ocr_only",
}


class RAGService:
    """Document processing and vector indexing pipeline."""

    def process_and_embed_file(self, db: Session, file_entity: KnowledgeFile, kb_entity: KnowledgeBase):
        logger.info(f"Start processing document: {file_entity.file_name}")

        chunk_size = file_entity.custom_chunk_size or kb_entity.default_chunk_size
        chunk_overlap = file_entity.custom_chunk_overlap or kb_entity.default_chunk_overlap

        # Safety check: overlap must be less than size
        if chunk_overlap >= chunk_size:
            chunk_overlap = max(0, chunk_size // 5)
            logger.warning(
                f"chunk_overlap >= chunk_size for file {file_entity.file_name}, "
                f"reset overlap to {chunk_overlap}"
            )

        full_text = self._extract_text(file_entity, kb_entity)
        if not full_text or not full_text.strip():
            logger.warning(f"No text extracted for file: {file_entity.file_name}")
            return

        chunks = self._split_text(full_text, chunk_size, chunk_overlap, file_entity)
        if not chunks:
            logger.warning(f"No chunks produced for file: {file_entity.file_name}")
            return

        repo = FileRepo(db)
        chunk_entities = [
            DocumentChunk(
                kb_id=file_entity.kb_id,
                file_id=file_entity.id,
                chunk_index=index,
                content=chunk.page_content[:65535],  # Guard against column overflow
                char_count=len(chunk.page_content),
            )
            for index, chunk in enumerate(chunks)
        ]
        saved_chunks = repo.bulk_create_chunks(chunk_entities)

        vectors = get_embeddings().embed_documents([chunk.content for chunk in saved_chunks])
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
        file_ext = file_entity.file_type.lower().strip(".")

        with tempfile.TemporaryDirectory() as temp_dir:
            local_file_path = os.path.join(temp_dir, file_entity.file_name)
            response = minio_repo.get_file_stream(file_entity.minio_object_name)
            with open(local_file_path, "wb") as file_obj:
                file_obj.write(response.read())
            response.close()
            response.release_conn()

            # ── Pure image files: OCR + store image reference ─────
            if file_ext in IMAGE_EXTENSIONS:
                return self._extract_from_image(local_file_path, file_entity, kb_entity, temp_dir)

            # ── Structured documents (PDF, DOCX, XLSX, etc.) ─────
            return self._extract_from_document(local_file_path, file_entity, kb_entity, temp_dir, file_ext)

    def _extract_from_image(
        self,
        local_file_path: str,
        file_entity: KnowledgeFile,
        kb_entity: KnowledgeBase,
        temp_dir: str,
    ) -> str:
        """Handle standalone image files: run OCR and store a persistent reference."""
        # Upload the image to persistent MinIO storage
        img_object_name = self._upload_image_to_minio(local_file_path, kb_entity.id)

        # Try OCR via unstructured
        ocr_text = ""
        try:
            elements = partition(
                filename=local_file_path,
                strategy="ocr_only",
                languages=["chi_sim", "eng"],
            )
            ocr_text = "\n\n".join(str(el) for el in elements if str(el).strip())
        except Exception as e:
            logger.warning(f"OCR failed for image {file_entity.file_name}: {e}")

        # Build combined text: image reference + OCR text
        parts = [f"[图片文件: {file_entity.file_name}]"]
        parts.append(f"[存储路径: minio://{img_object_name}]")
        if ocr_text:
            parts.append(f"[图片OCR文本]\n{ocr_text}")
        else:
            parts.append("[无可识别文本]")

        return "\n\n".join(parts)

    def _extract_from_document(
        self,
        local_file_path: str,
        file_entity: KnowledgeFile,
        kb_entity: KnowledgeBase,
        temp_dir: str,
        file_ext: str,
    ) -> str:
        """Handle structured documents (PDF, DOCX, PPTX, etc.)."""
        strategy = _STRATEGY_MAP.get(file_ext, "auto")

        partition_kwargs = {
            "filename": local_file_path,
            "strategy": strategy,
            "extract_image_block_types": ["Image", "Table"],
            "extract_image_block_output_dir": temp_dir,
        }
        # Add OCR languages for hi_res PDF strategy
        if strategy == "hi_res":
            partition_kwargs["languages"] = ["chi_sim", "eng"]

        try:
            elements = partition(**partition_kwargs)
        except Exception as e:
            logger.error(f"Partition failed for {file_entity.file_name}: {e}")
            # Fallback: try basic auto strategy
            elements = partition(filename=local_file_path, strategy="auto")

        full_text = ""
        for element in elements:
            if (
                isinstance(element, (Image, Table))
                and hasattr(element.metadata, "image_path")
                and element.metadata.image_path
            ):
                img_local_path = element.metadata.image_path
                if os.path.exists(img_local_path):
                    # Upload image to persistent MinIO path (not presigned URL)
                    img_object_name = self._upload_image_to_minio(img_local_path, kb_entity.id)

                    # Use persistent MinIO path reference instead of expiring presigned URL
                    full_text += f"\n\n[文档插图: minio://{img_object_name}]\n\n"

                    # If it's a table, also extract text content
                    if isinstance(element, Table):
                        table_text = str(element).strip()
                        if table_text:
                            full_text += f"[表格内容]\n{table_text}\n\n"
                else:
                    # Image path doesn't exist, just use text representation
                    full_text += str(element) + "\n\n"
            else:
                full_text += str(element) + "\n\n"
        return full_text

    def _upload_image_to_minio(self, local_path: str, kb_id: int) -> str:
        """Upload a local image file to MinIO and return the object name."""
        img_ext = os.path.splitext(local_path)[1].lower()
        img_object_name = f"kb_{kb_id}/images/{uuid.uuid4().hex}{img_ext}"

        with open(local_path, "rb") as img_file:
            img_bytes = img_file.read()
            content_type = f"image/{img_ext.strip('.')}"
            if img_ext in (".jpg", ".jpeg"):
                content_type = "image/jpeg"
            minio_repo.upload_file_bytes(
                img_object_name,
                img_bytes,
                content_type=content_type,
            )
        return img_object_name

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
