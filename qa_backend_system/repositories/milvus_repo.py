from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, MilvusClient, utility

from core.config import settings
from core.logger import logger
from core.milvus import DEFAULT_MILVUS_ALIAS, ensure_milvus_connection


class MilvusRepo:
    """Milvus access wrapper for chunk vectors."""

    def __init__(self):
        self.alias = DEFAULT_MILVUS_ALIAS
        self.collection_name = "qa_knowledge_collection"
        self.vector_dim = 4096
        self.client = MilvusClient(uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}")

    def ensure_collection(self):
        try:
            ensure_milvus_connection(self.alias)
            if not utility.has_collection(self.collection_name, using=self.alias):
                self._create_collection()
            else:
                self._validate_collection()
        except Exception as exc:
            logger.error(f"Failed to ensure Milvus collection: {exc}")
            raise

    def _load_collection(self):
        collection = Collection(self.collection_name, using=self.alias)
        load_state = utility.load_state(self.collection_name, using=self.alias)
        if str(load_state).upper() != "LOADED":
            collection.load()
            logger.info(f"Milvus collection '{self.collection_name}' loaded")
        return collection

    def _create_collection(self):
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="chunk_id", dtype=DataType.INT64, description="Chunk ID"),
            FieldSchema(name="kb_id", dtype=DataType.INT64, description="Knowledge Base ID"),
            FieldSchema(name="file_id", dtype=DataType.INT64, description="File ID"),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535, description="Chunk text"),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.vector_dim),
        ]
        schema = CollectionSchema(fields=fields, description="QA document chunk collection")
        collection = Collection(name=self.collection_name, schema=schema, using=self.alias)
        collection.create_index(
            field_name="embedding",
            index_params={
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024},
            },
        )
        logger.info(f"Milvus collection '{self.collection_name}' created")

    def _validate_collection(self):
        collection = Collection(self.collection_name, using=self.alias)
        field_map = {field.name: field for field in collection.schema.fields}
        required_fields = {"chunk_id", "kb_id", "file_id", "text", "embedding"}
        missing_fields = required_fields - set(field_map)
        if missing_fields:
            raise RuntimeError(
                f"Milvus collection '{self.collection_name}' schema is outdated. "
                f"Missing fields: {sorted(missing_fields)}. Please recreate the collection."
            )

        embedding_field = field_map["embedding"]
        dim = getattr(embedding_field, "params", {}).get("dim")
        if dim != self.vector_dim:
            raise RuntimeError(
                f"Milvus collection '{self.collection_name}' has embedding dim={dim}, "
                f"expected {self.vector_dim}. Please recreate the collection."
            )

    def insert_chunks(self, rows: list[dict]):
        if not rows:
            return
        self.ensure_collection()
        self.client.insert(collection_name=self.collection_name, data=rows)

    def search_chunks(self, kb_id: int, query_vector: list[float], top_k: int = 5) -> list[dict]:
        self.ensure_collection()
        self._load_collection()
        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            limit=top_k,
            filter=f"kb_id == {kb_id}",
            output_fields=["chunk_id", "kb_id", "file_id", "text"],
        )
        return results[0] if results else []

    def search_chunks_across_kbs(self, query_vector: list[float], top_k: int = 8) -> list[dict]:
        self.ensure_collection()
        self._load_collection()
        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            limit=top_k,
            output_fields=["chunk_id", "kb_id", "file_id", "text"],
        )
        return results[0] if results else []

    def delete_chunks_by_file_id(self, file_id: int):
        self.ensure_collection()
        self._load_collection()
        self.client.delete(self.collection_name, filter=f"file_id == {file_id}")
        logger.info(f"Deleted Milvus vectors for file_id={file_id}")


milvus_repo = MilvusRepo()
