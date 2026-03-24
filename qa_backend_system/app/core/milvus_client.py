from langchain_milvus import Milvus
from .embedding import get_e5_embeddings


def get_vector_store(collection_name: str = "qa_collection"):
    """
    获取装载了 Custom E5 的 Milvus 向量库实例
    """
    # 1. 初始化你的自定义 E5 模型
    embeddings = get_e5_embeddings()

    # 2. 将其传递给 LangChain 的 Milvus 包装器
    vector_store = Milvus(
        embedding_function=embeddings,
        connection_args={"uri": "http://127.0.0.1:19530"},
        collection_name=collection_name,
        auto_id=True,
        drop_old=False
    )
    return vector_store