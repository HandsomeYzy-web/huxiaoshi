from typing import List

import requests
from langchain_core.embeddings import Embeddings


class CustomE5Embeddings(Embeddings):
    """E5 embedding adapter compatible with LangChain's Embeddings interface."""

    def __init__(self, api_base: str, api_key: str, model: str, timeout: int = 60):
        base = api_base.rstrip("/")
        self.api_url = f"{base}/embeddings" if base.endswith("/v1") else base
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        payload = {
            "model": self.model,
            "input": texts,
        }
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]

    def embed_query(self, text: str) -> List[float]:
        query_text = (
            "Instruct: Given a web search query, retrieve relevant passages that answer the query.\n"
            f"Query: {text}"
        )
        payload = {
            "model": self.model,
            "input": [query_text],
        }
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
