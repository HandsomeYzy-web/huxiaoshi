"""
LLM 服务层：统一管理 ChatOpenAI 实例的创建与缓存，
提供同步调用、流式调用、带 JSON Schema 约束的调用等能力。
支持任意 OpenAI 兼容接口（dashscope、ollama、DeepSeek 等）。
"""

import threading

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings
from core.database import SessionLocal


class LLMService:
    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你是知识库问答助手。请严格依据提供的检索内容回答问题。"
                        "如果检索内容不足以支持结论，直接回答：根据当前知识库内容无法确定。"
                        "回答要准确、简洁，并尽量综合多个知识库的信息。"
                    ),
                ),
                ("human", "问题：{question}\n\n检索内容：\n{context_block}"),
            ]
        )
        self.casual_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你是一个友好的智能助手。用户正在与你闲聊，请自然、亲切地回答。"
                        "回答要简洁明了，语气友好，可以适当加入表情或幽默。"
                    ),
                ),
                ("human", "{question}"),
            ]
        )
        self.output_parser = StrOutputParser()
        # Lazily initialized — avoids creating ChatOpenAI on every request
        self._model: ChatOpenAI | None = None
        self._streaming_model: ChatOpenAI | None = None
        self._lock = threading.Lock()
        # Cache the resolved config so we know which model_name to report
        self._resolved_base_url: str | None = None
        self._resolved_api_key: str | None = None
        self._resolved_model_name: str | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_llm_config(self) -> tuple[str, str, str] | None:
        """Return (base_url, api_key, model_name) from DB active config."""
        try:
            db = SessionLocal()
            try:
                from repositories.model_config_repo import ModelConfigRepo
                active = ModelConfigRepo(db).get_active("llm")
                if active:
                    return active.api_base_url, active.api_key, active.model_name
            finally:
                db.close()
        except Exception:
            pass
        return None

    def _build_model(self, streaming: bool) -> ChatOpenAI | None:
        cfg = self._resolve_llm_config()
        if not cfg:
            return None
        base_url, api_key, model_name = cfg
        self._resolved_base_url = base_url
        self._resolved_api_key = api_key
        self._resolved_model_name = model_name
        return ChatOpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            model=model_name,
            temperature=0.1,
            streaming=streaming,
            request_timeout=settings.LLM_TIMEOUT,
        )

    @property
    def model(self) -> ChatOpenAI | None:
        """Non-streaming model, lazily initialized (thread-safe)."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._build_model(streaming=False)
        return self._model

    @property
    def streaming_model(self) -> ChatOpenAI | None:
        """Streaming model, lazily initialized (thread-safe)."""
        if self._streaming_model is None:
            with self._lock:
                if self._streaming_model is None:
                    self._streaming_model = self._build_model(streaming=True)
        return self._streaming_model

    @staticmethod
    def _build_context_block(contexts: list[str]) -> str:
        return "\n\n".join(
            f"[片段 {i + 1}]\n{ctx}" for i, ctx in enumerate(contexts)
        )

    @staticmethod
    def _fallback_response(contexts: list[str]) -> str:
        snippet = "\n\n".join(contexts[:3])
        return (
            "未配置生成模型，当前返回检索到的高相关片段供前端展示。\n\n"
            f"{snippet}"
        )

    # ------------------------------------------------------------------
    # Public API (signatures unchanged for backward compatibility)
    # ------------------------------------------------------------------

    def generate_answer(self, question: str, contexts: list[str]) -> tuple[str, str | None]:
        if self.model is None:
            return self._fallback_response(contexts), None

        chain = self.prompt | self.model | self.output_parser
        answer = chain.invoke(
            {"question": question, "context_block": self._build_context_block(contexts)}
        )
        return answer, self._resolved_model_name

    def stream_answer(self, question: str, contexts: list[str]):
        """流式生成回答，生成器返回 (chunk: str, is_model_info: bool, model_name: str | None)"""
        if self.streaming_model is None:
            yield self._fallback_response(contexts), False, None
            return

        # Signal the model name first
        yield "", True, self._resolved_model_name

        chain = self.prompt | self.streaming_model | self.output_parser
        for chunk in chain.stream(
            {"question": question, "context_block": self._build_context_block(contexts)}
        ):
            if chunk:
                yield chunk, False, None

    # ------------------------------------------------------------------
    # Casual chat (no retrieval context)
    # ------------------------------------------------------------------

    def generate_casual_answer(self, question: str) -> tuple[str, str | None]:
        """Non-streaming casual chat answer."""
        if self.model is None:
            return "我是知识库问答助手，目前 LLM 未配置，暂时无法闲聊。", None

        chain = self.casual_prompt | self.model | self.output_parser
        answer = chain.invoke({"question": question})
        return answer, self._resolved_model_name

    def stream_casual_answer(self, question: str):
        """流式闲聊回答，生成器返回 (chunk: str, is_model_info: bool, model_name: str | None)"""
        if self.streaming_model is None:
            yield "我是知识库问答助手，目前 LLM 未配置，暂时无法闲聊。", False, None
            return

        yield "", True, self._resolved_model_name

        chain = self.casual_prompt | self.streaming_model | self.output_parser
        for chunk in chain.stream({"question": question}):
            if chunk:
                yield chunk, False, None


llm_service = LLMService()
