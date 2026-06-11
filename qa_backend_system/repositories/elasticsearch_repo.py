"""
Elasticsearch 向量数据库仓储层：封装向量索引的创建、插入、检索、删除等操作。
每个知识库对应一个独立的 Elasticsearch index（与原 Milvus collection 一一对应）。
"""

from elasticsearch.helpers import bulk

from core.elasticsearch import get_es_client
from core.exceptions import ExternalServiceError
from core.logger import logger


class ElasticsearchRepo:
    """Elasticsearch 向量数据库访问封装 — 每个知识库拥有独立的 index。"""

    def __init__(self):
        self.client = get_es_client()

    @property
    def vector_dim(self) -> int:
        """从当前激活的 Embedding 模型配置中获取向量维度。"""
        from services.embeddings import get_embedding_vector_dim
        return get_embedding_vector_dim()

    @staticmethod
    def _index_name(kb_id: int) -> str:
        """根据知识库 ID 生成对应的 Elasticsearch index 名称。"""
        return f"kb_chunks_{kb_id}"

    def ensure_index(self, kb_id: int):
        """确保指定知识库的 Elasticsearch index 已存在，不存在则自动创建。"""
        index_name = self._index_name(kb_id)
        try:
            if not self.client.indices.exists(index=index_name):
                self._create_index(index_name)
            else:
                self._validate_index(index_name)
        except Exception as exc:
            logger.error(f"Failed to ensure Elasticsearch index for kb_id={kb_id}: {exc}")
            raise

    def _create_index(self, index_name: str):
        mappings = {
            "properties": {
                "chunk_id": {"type": "long"},
                "kb_id": {"type": "long"},
                "file_id": {"type": "long"},
                "text": {"type": "text"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": self.vector_dim,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        }
        self.client.indices.create(index=index_name, mappings=mappings)
        logger.info(f"Elasticsearch index '{index_name}' created")

    def _validate_index(self, index_name: str):
        mapping = self.client.indices.get_mapping(index=index_name)
        properties = mapping.get(index_name, {}).get("mappings", {}).get("properties", {})
        required_fields = {"chunk_id", "kb_id", "file_id", "text", "embedding"}
        missing_fields = required_fields - set(properties)
        if missing_fields:
            raise RuntimeError(
                f"Elasticsearch index '{index_name}' mapping is outdated. "
                f"Missing fields: {sorted(missing_fields)}. Please recreate the index."
            )

        dim = properties.get("embedding", {}).get("dims")
        if dim != self.vector_dim:
            raise RuntimeError(
                f"Elasticsearch index '{index_name}' has embedding dims={dim}, "
                f"expected {self.vector_dim}. Please recreate the index."
            )

    def insert_chunks(self, kb_id: int, rows: list[dict]):
        """将文档分段的向量数据批量插入到 Elasticsearch index 中。"""
        if not rows:
            return
        self.ensure_index(kb_id)
        index_name = self._index_name(kb_id)
        actions = [
            {
                "_index": index_name,
                # 使用 chunk_id 作为文档 _id，保证幂等写入与按切片删除。
                "_id": str(row["chunk_id"]),
                "_source": {
                    "chunk_id": row["chunk_id"],
                    "kb_id": row["kb_id"],
                    "file_id": row["file_id"],
                    "text": row["text"],
                    "embedding": row["embedding"],
                },
            }
            for row in rows
        ]
        bulk(self.client, actions)
        self.client.indices.refresh(index=index_name)

    def search_chunks(
        self,
        kb_id: int,
        query_vector: list[float],
        top_k: int = 5,
        vector_dim: int | None = None,
    ) -> list[dict]:
        """在指定知识库的 index 中进行向量相似度（kNN）检索。"""
        index_name = self._index_name(kb_id)
        if not self.client.indices.exists(index=index_name):
            return []
        response = self.client.search(
            index=index_name,
            knn={
                "field": "embedding",
                "query_vector": query_vector,
                "k": top_k,
                "num_candidates": max(top_k * 4, 100),
            },
            source=["chunk_id", "kb_id", "file_id", "text"],
            size=top_k,
        )
        hits = response.get("hits", {}).get("hits", [])
        return [self._format_hit(hit) for hit in hits]

    def search_chunks_across_kbs(self, kb_ids: list[int], query_vector: list[float], top_k: int = 8) -> list[dict]:
        """跨多个知识库的 index 进行向量检索并合并排序结果。"""
        all_results = []
        for kid in kb_ids:
            try:
                results = self.search_chunks(kid, query_vector, top_k=top_k)
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Search failed for kb_id={kid}: {e}")
        # Sort by score descending (higher = more similar for cosine)
        all_results.sort(key=lambda x: float(x.get("distance", 0.0)), reverse=True)
        return all_results[:top_k]

    @staticmethod
    def _format_hit(hit: dict) -> dict:
        """将 ES 命中结果归一化为兼容旧 Milvus 返回结构的字典。

        同时提供顶层扁平字段与嵌套的 ``entity`` 子字典、以及 ``distance``/``score``，
        以兼容仓库内不同调用方对结果结构的两种读取方式。
        """
        source = hit.get("_source", {})
        score = float(hit.get("_score", 0.0))
        entity = {
            "chunk_id": source.get("chunk_id"),
            "kb_id": source.get("kb_id"),
            "file_id": source.get("file_id"),
            "text": source.get("text", ""),
        }
        return {
            "id": hit.get("_id"),
            "distance": score,
            "score": score,
            **entity,
            "entity": entity,
        }

    def delete_chunks_by_file_id(self, kb_id: int, file_id: int):
        """删除指定文件在 Elasticsearch 中的所有向量数据。"""
        try:
            index_name = self._index_name(kb_id)
            if not self.client.indices.exists(index=index_name):
                return
            self.client.delete_by_query(
                index=index_name,
                query={"term": {"file_id": file_id}},
                refresh=True,
            )
            logger.info(f"Deleted Elasticsearch vectors for file_id={file_id} in {index_name}")
        except Exception as e:
            logger.error(f"Elasticsearch 删除失败 (file_id={file_id}): {e}")
            raise ExternalServiceError(f"向量库删除失败: file_id={file_id}")

    def delete_chunk_by_chunk_id(self, kb_id: int, chunk_id: int):
        """删除指定切片在 Elasticsearch 中的向量数据。"""
        try:
            index_name = self._index_name(kb_id)
            if not self.client.indices.exists(index=index_name):
                return
            # ignore_status=404：切片在 ES 中不存在时静默跳过，不视为错误。
            self.client.options(ignore_status=404).delete(
                index=index_name, id=str(chunk_id), refresh=True
            )
            logger.info(f"Deleted Elasticsearch vector for chunk_id={chunk_id} in {index_name}")
        except Exception as e:
            logger.error(f"Elasticsearch 切片删除失败 (chunk_id={chunk_id}): {e}")
            raise ExternalServiceError(f"向量库删除失败: chunk_id={chunk_id}")

    def delete_chunks_by_kb_id(self, kb_id: int):
        """删除整个知识库对应的 Elasticsearch index（用于知识库删除或重建）。"""
        try:
            index_name = self._index_name(kb_id)
            if self.client.indices.exists(index=index_name):
                self.client.indices.delete(index=index_name)
                logger.info(f"Dropped Elasticsearch index: {index_name}")
            else:
                logger.info(f"Elasticsearch index '{index_name}' not found, nothing to drop")
        except Exception as e:
            logger.error(f"Elasticsearch 删除失败 (kb_id={kb_id}): {e}")
            raise ExternalServiceError(f"向量库删除失败: kb_id={kb_id}")


es_repo = ElasticsearchRepo()
