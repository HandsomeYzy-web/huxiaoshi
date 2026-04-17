"""
LLM 服务层：统一管理 ChatOpenAI 实例的创建与缓存，
提供同步调用、流式调用、带 JSON Schema 约束的调用等能力。
支持任意 OpenAI 兼容接口（dashscope、ollama、DeepSeek 等）。
"""

import json
import threading

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings
from core.database import SessionLocal
from core.logger import logger
from core.url_utils import normalize_llm_base_url


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
        self.merged_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你是一个智能助手，能同时利用知识库文档和数据库查询结果来回答用户问题。\n"
                        "请根据下方提供的信息来源回答问题：\n"
                        "- 如果有「数据库查询结果」且与问题相关，请基于数据进行分析和总结\n"
                        "- 如果有「知识库检索内容」且与问题相关，请基于文档内容回答\n"
                        "- 如果两者都有相关内容，请综合两方面信息给出完整回答\n"
                        "- 如果两者都没有有效内容，说明该问题超出了当前系统的知识范围，"
                        "可以尝试以闲聊方式友好回答，或者告知用户暂时无法回答\n\n"
                        "回答要准确、简洁、有条理。如果引用了数据，请适当使用表格或列表展示。"
                    ),
                ),
                ("human", "问题：{question}\n\n{sources_block}"),
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

    def _resolve_llm_config(self) -> dict | None:
        """Return config dict from DB active config, including provider & extra_params."""
        try:
            db = SessionLocal()
            try:
                from repositories.model_config_repo import ModelConfigRepo
                active = ModelConfigRepo(db).get_active("llm")
                if active:
                    extra = {}
                    if active.extra_params:
                        try:
                            extra = json.loads(active.extra_params)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    return {
                        "base_url": active.api_base_url,
                        "api_key": active.api_key,
                        "model_name": active.model_name,
                        "provider": active.provider,
                        "extra_params": extra,
                    }
            finally:
                db.close()
        except Exception:
            pass
        return None

    def _build_model(self, streaming: bool) -> ChatOpenAI | None:
        cfg = self._resolve_llm_config()
        if not cfg:
            return None
        base_url = cfg["base_url"]
        api_key = cfg["api_key"]
        model_name = cfg["model_name"]
        extra = cfg.get("extra_params", {})

        self._resolved_base_url = base_url
        self._resolved_api_key = api_key
        self._resolved_model_name = model_name

        kwargs: dict = dict(
            base_url=normalize_llm_base_url(base_url),
            api_key=api_key,
            model=model_name,
            temperature=0.1,
            streaming=streaming,
            request_timeout=settings.LLM_TIMEOUT,
        )

        # extra_params 中的可选覆盖
        if "temperature" in extra:
            kwargs["temperature"] = float(extra["temperature"])
        if extra.get("supports_stream") is False and streaming:
            # 该模型声明不支持流式，强制关闭
            kwargs["streaming"] = False

        return ChatOpenAI(**kwargs)

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

        has_content = False
        try:
            chain = self.prompt | self.streaming_model | self.output_parser
            for chunk in chain.stream(
                {"question": question, "context_block": self._build_context_block(contexts)}
            ):
                if chunk:
                    has_content = True
                    yield chunk, False, None
        except Exception as e:
            logger.warning(f"Streaming failed: {e}, falling back to non-streaming")

        if not has_content:
            # 流式无输出时降级为非流式调用（兼容 DeepSeek-R1 等推理模型）
            logger.info("No streaming chunks received, trying non-streaming fallback")
            try:
                answer, _ = self.generate_answer(question, contexts)
                if answer:
                    yield answer, False, None
                else:
                    yield "抱歉，模型未返回有效内容，请检查模型配置。", False, None
            except Exception as fallback_err:
                logger.error(f"Non-streaming fallback also failed: {fallback_err}")
                yield f"生成回答失败，请检查模型配置是否正确: {fallback_err}", False, None

    # ------------------------------------------------------------------
    # Merged answer (combine doc_search + text2sql results)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_sources_block(
        contexts: list[str] | None,
        sql: str | None,
        sql_columns: list[str] | None,
        sql_rows: list[dict] | None,
    ) -> str:
        """Build a unified sources block for the merged prompt."""
        parts: list[str] = []

        if sql and sql_columns and sql_rows is not None:
            header = " | ".join(sql_columns)
            lines = [header, "-" * len(header)]
            for row in sql_rows[:50]:
                lines.append(" | ".join(str(row.get(c, "")) for c in sql_columns))
            if len(sql_rows) > 50:
                lines.append(f"... 共 {len(sql_rows)} 行，仅展示前 50 行")
            result_text = "\n".join(lines) if sql_rows else "查询结果为空"
            parts.append(f"【数据库查询结果】\n执行 SQL：{sql}\n\n{result_text}")
        elif sql:
            parts.append(f"【数据库查询】\nSQL 执行失败或无结果")

        if contexts:
            ctx_block = "\n\n".join(
                f"[片段 {i + 1}]\n{ctx}" for i, ctx in enumerate(contexts)
            )
            parts.append(f"【知识库检索内容】\n{ctx_block}")

        if not parts:
            parts.append("【无有效信息来源】\n数据库查询和知识库检索均未返回相关内容。")

        return "\n\n---\n\n".join(parts)

    def stream_merged_answer(
        self,
        question: str,
        contexts: list[str] | None = None,
        sql: str | None = None,
        sql_columns: list[str] | None = None,
        sql_rows: list[dict] | None = None,
    ):
        """流式合并回答，综合文档检索和数据库查询结果。
        生成器返回 (chunk: str, is_model_info: bool, model_name: str | None)
        """
        if self.streaming_model is None:
            yield "LLM 未配置，无法生成回答。", False, None
            return

        yield "", True, self._resolved_model_name

        sources_block = self._build_sources_block(contexts, sql, sql_columns, sql_rows)

        has_content = False
        try:
            chain = self.merged_prompt | self.streaming_model | self.output_parser
            for chunk in chain.stream({"question": question, "sources_block": sources_block}):
                if chunk:
                    has_content = True
                    yield chunk, False, None
        except Exception as e:
            logger.warning(f"Merged streaming failed: {e}, falling back to non-streaming")

        if not has_content:
            logger.info("No merged streaming chunks, trying non-streaming fallback")
            try:
                chain = self.merged_prompt | self.model | self.output_parser
                answer = chain.invoke({"question": question, "sources_block": sources_block})
                if answer:
                    yield answer, False, None
                else:
                    yield "抱歉，模型未返回有效内容。", False, None
            except Exception as fallback_err:
                logger.error(f"Merged non-streaming fallback failed: {fallback_err}")
                yield f"生成回答失败: {fallback_err}", False, None


llm_service = LLMService()
