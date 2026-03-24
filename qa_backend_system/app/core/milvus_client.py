import os
from pymilvus import connections, utility
from langchain_milvus import Milvus
from .embedding import get_e5_embeddings

MILVUS_HOST = os.getenv("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
MILVUS_ALIAS = os.getenv("MILVUS_ALIAS", "default")


def ensure_milvus_connection():
    print("A. ensure_milvus_connection start")
    print(f"B. host={MILVUS_HOST}, port={MILVUS_PORT}, alias={MILVUS_ALIAS}")

    # 先断开旧连接，避免 alias 状态脏掉（很关键）
    try:
        if connections.has_connection(MILVUS_ALIAS):
            print(f"C. disconnect old alias={MILVUS_ALIAS}")
            connections.disconnect(MILVUS_ALIAS)
    except Exception as e:
        print(f"C. disconnect old alias failed: {e}")

    # 重新建立连接
    print("D. connecting...")
    connections.connect(
        alias=MILVUS_ALIAS,
        host=MILVUS_HOST,
        port=MILVUS_PORT,
    )
    print("E. connect success")

    # 主动验证
    collections = utility.list_collections(using=MILVUS_ALIAS)
    print(f"F. list_collections success, collections={collections}")


def get_vector_store(collection_name: str = "qa_collection"):
    print("0. start get_vector_store")

    ensure_milvus_connection()

    embeddings = get_e5_embeddings()
    print("1. embeddings ready")

    print("2. before Milvus(...)")

    vector_store = Milvus(
        embedding_function=embeddings,
        collection_name=collection_name,
        connection_args={
            "host": MILVUS_HOST,
            "port": MILVUS_PORT,
            "alias": MILVUS_ALIAS,   # 关键：显式传 alias
        },
        auto_id=True,
    )

    print("3. after Milvus(...)")
    return vector_store