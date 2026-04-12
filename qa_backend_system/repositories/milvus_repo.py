"""
Milvus 向量数据库仓储层：封装向量集合的创建、插入、检索、删除等操作。
每个知识库对应一个独立的 Milvus collection。
"""

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, MilvusClient, utility

from core.config import settings
from core.exceptions import ExternalServiceError
from core.logger import logger
from core.milvus import DEFAULT_MILVUS_ALIAS, ensure_milvus_connection


class MilvusRepo:
    """Milvus 向量数据库访问封装 — 每个知识库拥有独立的 collection。"""

    def __init__(self):
        self.alias = DEFAULT_MILVUS_ALIAS
        self.client = MilvusClient(uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}")

    @property
    def vector_dim(self) -> int:
        """从当前激活的 Embedding 模型配置中获取向量维度。"""
        from services.embeddings import get_embedding_vector_dim
        return get_embedding_vector_dim()

    @staticmethod
    def _collection_name(kb_id: int) -> str:
        """根据知识库 ID 生成对应的 Milvus collection 名称。"""
        return f"kb_collection_{kb_id}"

    def ensure_collection(self, kb_id: int):
        """确保指定知识库的 Milvus collection 已存在，不存在则自动创建。"""
        collection_name = self._collection_name(kb_id)
        try:
            ensure_milvus_connection(self.alias)
            if not utility.has_collection(collection_name, using=self.alias):
                self._create_collection(collection_name)
            else:
                self._validate_collection(collection_name)
        except Exception as exc:
            logger.error(f"Failed to ensure Milvus collection for kb_id={kb_id}: {exc}")
            raise

    def _load_collection(self, collection_name: str):
        collection = Collection(collection_name, using=self.alias)
        load_state = utility.load_state(collection_name, using=self.alias)
        if str(load_state).upper() != "LOADED":
            collection.load()
            logger.info(f"Milvus collection '{collection_name}' loaded")
        return collection

    def _create_collection(self, collection_name: str):
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="chunk_id", dtype=DataType.INT64, description="Chunk ID"),
            FieldSchema(name="kb_id", dtype=DataType.INT64, description="Knowledge Base ID"),
            FieldSchema(name="file_id", dtype=DataType.INT64, description="File ID"),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535, description="Chunk text"),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.vector_dim),
        ]
        schema = CollectionSchema(fields=fields, description=f"Document chunks for {collection_name}")
        collection = Collection(name=collection_name, schema=schema, using=self.alias)
        collection.create_index(
            field_name="embedding",
            index_params={
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024},
            },
        )
        logger.info(f"Milvus collection '{collection_name}' created")

    def _validate_collection(self, collection_name: str):
        collection = Collection(collection_name, using=self.alias)
        field_map = {field.name: field for field in collection.schema.fields}
        required_fields = {"chunk_id", "kb_id", "file_id", "text", "embedding"}
        missing_fields = required_fields - set(field_map)
        if missing_fields:
            raise RuntimeError(
                f"Milvus collection '{collection_name}' schema is outdated. "
                f"Missing fields: {sorted(missing_fields)}. Please recreate the collection."
            )

        embedding_field = field_map["embedding"]
        dim = getattr(embedding_field, "params", {}).get("dim")
        if dim != self.vector_dim:
            raise RuntimeError(
                f"Milvus collection '{collection_name}' has embedding dim={dim}, "
                f"expected {self.vector_dim}. Please recreate the collection."
            )

    def insert_chunks(self, kb_id: int, rows: list[dict]):
        """将文档分段的向量数据批量插入到 Milvus collection 中。"""
        if not rows:
            return
        self.ensure_collection(kb_id)
        collection_name = self._collection_name(kb_id)
        self.client.insert(collection_name=collection_name, data=rows)

    def search_chunks(self, kb_id: int, query_vector: list[float], top_k: int = 5) -> list[dict]:
        """在指定知识库的 collection 中进行向量相似度检索。"""
        collection_name = self._collection_name(kb_id)
        self.ensure_collection(kb_id)
        self._load_collection(collection_name)
        results = self.client.search(
            collection_name=collection_name,
            data=[query_vector],
            limit=top_k,
            output_fields=["chunk_id", "kb_id", "file_id", "text"],
        )
        return results[0] if results else []

    def search_chunks_across_kbs(self, kb_ids: list[int], query_vector: list[float], top_k: int = 8) -> list[dict]:
        """跨多个知识库的 collection 进行向量检索并合并排序结果。"""
        all_results = []
        for kid in kb_ids:
            try:
                results = self.search_chunks(kid, query_vector, top_k=top_k)
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Search failed for kb_id={kid}: {e}")
        # Sort by distance descending (higher = more similar for COSINE)
        all_results.sort(key=lambda x: float(x.get("distance", 0.0)), reverse=True)
        return all_results[:top_k]

    def delete_chunks_by_file_id(self, kb_id: int, file_id: int):
        """删除指定文件在 Milvus 中的所有向量数据。"""
        try:
            collection_name = self._collection_name(kb_id)
            self.ensure_collection(kb_id)
            self._load_collection(collection_name)
            self.client.delete(collection_name, filter=f"file_id == {file_id}")
            logger.info(f"Deleted Milvus vectors for file_id={file_id} in {collection_name}")
        except Exception as e:
            logger.error(f"Milvus 删除失败 (file_id={file_id}): {e}")
            raise ExternalServiceError(f"向量库删除失败: file_id={file_id}")

    def delete_chunks_by_kb_id(self, kb_id: int):
        """删除整个知识库对应的 Milvus collection（用于知识库删除或重建）。"""
        try:
            collection_name = self._collection_name(kb_id)
            ensure_milvus_connection(self.alias)
            if utility.has_collection(collection_name, using=self.alias):
                utility.drop_collection(collection_name, using=self.alias)
                logger.info(f"Dropped Milvus collection: {collection_name}")
            else:
                logger.info(f"Milvus collection '{collection_name}' not found, nothing to drop")
        except Exception as e:
            logger.error(f"Milvus 删除失败 (kb_id={kb_id}): {e}")
            raise ExternalServiceError(f"向量库删除失败: kb_id={kb_id}")


milvus_repo = MilvusRepo()
