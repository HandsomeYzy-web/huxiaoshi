from pymilvus import connections, utility, Collection, CollectionSchema, FieldSchema, DataType
from core.config import settings
from core.logger import logger


class MilvusRepo:
    """Milvus 向量库底层访问封装"""

    def __init__(self):
        self.alias = "default"
        self.collection_name = "qa_knowledge_collection"
        self.vector_dim = 1536  # 假设使用通义千问等主流 Embedding 模型的维度
        self._connect()

    def _connect(self):
        try:
            connections.connect(
                alias=self.alias,
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT
            )
            # 如果不存在，则初始化 Collection
            if not utility.has_collection(self.collection_name, using=self.alias):
                self._create_collection()
        except Exception as e:
            logger.error(f"❌ 连接 Milvus 失败: {e}")

    def _create_collection(self):
        """创建包含多租户/文件级别的 Schema"""
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="kb_id", dtype=DataType.INT64, description="知识库ID"),
            FieldSchema(name="file_id", dtype=DataType.INT64, description="文件ID (用于精准清理)"),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535, description="Chunk文本内容"),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.vector_dim)
        ]
        schema = CollectionSchema(fields=fields, description="RAG 知识库集合")
        collection = Collection(name=self.collection_name, schema=schema, using=self.alias)

        # 创建 IVF_FLAT 索引以加速检索
        index_params = {"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 1024}}
        collection.create_index(field_name="embedding", index_params=index_params)
        logger.info(f"✅ Milvus Collection '{self.collection_name}' 及索引创建成功")

    def delete_chunks_by_file_id(self, file_id: int):
        """
        核心方法：当用户【单独指定某一个文件的切分策略】时，
        必须先调用此方法清理该 file_id 之前的所有 Chunk，然后再重新入库。
        """
        collection = Collection(self.collection_name)
        collection.load()
        expr = f"file_id == {file_id}"
        collection.delete(expr)
        logger.info(f"已清理 Milvus 中 file_id={file_id} 的所有旧向量数据")


milvus_repo = MilvusRepo()  # 实例化单例