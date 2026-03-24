"""
自定义 E5 嵌入类，适配 LangChain 的 Embeddings 接口
- embed_documents: 用于知识库文档向量化，不加前缀
- embed_query: 用于用户提问向量化，自动加上 E5 要求的指令前缀
"""

import os
from typing import List
import requests
from langchain_core.embeddings import Embeddings

class CustomE5Embeddings(Embeddings):
    def __init__(self, api_base: str, api_key: str, model: str):
        if api_base.endswith("/v1"):
            self.api_url = f"{api_base}/embeddings"
        else:
            self.api_url = api_base
        self.api_key = api_key
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """用于知识库文档向量化（存入数据库时调用），不加前缀"""
        payload = {"model": self.model, "input": texts}
        response = requests.post(self.api_url, headers=self.headers, json=payload)
        response.raise_for_status()
        return [item["embedding"] for item in response.json()["data"]]

    def embed_query(self, text: str) -> List[float]:
        """用于用户提问向量化（检索时调用），自动加上 E5 要求的指令前缀"""
        query_text = f"Instruct: Given a web search query, retrieve relevant passages that answer the query.\nQuery: {text}"
        payload = {"model": self.model, "input": [query_text]}
        response = requests.post(self.api_url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

# 方便在其他模块中直接调用，避免重复代码
def get_e5_embeddings() -> CustomE5Embeddings:
    """从环境变量读取配置并实例化 E5 模型"""
    return CustomE5Embeddings(
        api_base=os.getenv("E5_API_BASE"), # 替换为你的默认地址
        api_key=os.getenv("E5_API_KEY"),
        model=os.getenv("E5_MODEL_NAME")
    )