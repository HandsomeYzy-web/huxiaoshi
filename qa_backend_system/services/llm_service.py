from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings


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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_configured(self) -> bool:
        return bool(
            settings.EFFECTIVE_LLM_BASE_URL
            and settings.EFFECTIVE_LLM_API_KEY
            and settings.EFFECTIVE_LLM_MODEL
        )

    def _build_model(self, streaming: bool) -> ChatOpenAI:
        return ChatOpenAI(
            base_url=settings.EFFECTIVE_LLM_BASE_URL.rstrip("/"),
            api_key=settings.EFFECTIVE_LLM_API_KEY,
            model=settings.EFFECTIVE_LLM_MODEL,
            temperature=0.1,
            streaming=streaming,
            request_timeout=settings.LLM_TIMEOUT,
        )

    @property
    def model(self) -> ChatOpenAI | None:
        """Non-streaming model, lazily initialized."""
        if not self._is_configured():
            return None
        if self._model is None:
            self._model = self._build_model(streaming=False)
        return self._model

    @property
    def streaming_model(self) -> ChatOpenAI | None:
        """Streaming model, lazily initialized."""
        if not self._is_configured():
            return None
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
        return answer, settings.EFFECTIVE_LLM_MODEL

    def stream_answer(self, question: str, contexts: list[str]):
        """流式生成回答，生成器返回 (chunk: str, is_model_info: bool, model_name: str | None)"""
        if self.streaming_model is None:
            yield self._fallback_response(contexts), False, None
            return

        # Signal the model name first
        yield "", True, settings.EFFECTIVE_LLM_MODEL

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
        return answer, settings.EFFECTIVE_LLM_MODEL

    def stream_casual_answer(self, question: str):
        """流式闲聊回答，生成器返回 (chunk: str, is_model_info: bool, model_name: str | None)"""
        if self.streaming_model is None:
            yield "我是知识库问答助手，目前 LLM 未配置，暂时无法闲聊。", False, None
            return

        yield "", True, settings.EFFECTIVE_LLM_MODEL

        chain = self.casual_prompt | self.streaming_model | self.output_parser
        for chunk in chain.stream({"question": question}):
            if chunk:
                yield chunk, False, None


llm_service = LLMService()
