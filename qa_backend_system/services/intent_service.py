"""
Intent Classification Service — 用 LLM 将用户输入分类为三种意图。

意图类型:
- casual_chat: 闲聊（问候、闲谈、与知识库/数据无关的问题）
- data_query:  查数据（用户想从业务数据库中查询结构化数据，适合 Text2SQL）
- doc_search:  查文档（用户想从知识库文档中检索信息，适合 RAG）
"""
from __future__ import annotations

import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings
from core.logger import logger

# 意图标识常量
INTENT_CASUAL_CHAT = "casual_chat"
INTENT_DATA_QUERY = "data_query"
INTENT_DOC_SEARCH = "doc_search"

ALL_INTENTS = {INTENT_CASUAL_CHAT, INTENT_DATA_QUERY, INTENT_DOC_SEARCH}

# 分类提示词
_CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "你是一个意图分类器。根据用户的问题，判断用户意图属于以下三类之一，只返回 JSON。\n\n"
            "意图类型：\n"
            "1. casual_chat — 闲聊、问候、与业务数据和文档无关的日常对话\n"
            "2. data_query — 用户想查询、统计、对比具体的业务数据（如销售额、用户数、订单量等结构化数据）{data_query_hint}\n"
            "3. doc_search — 用户想从知识库文档中检索信息（如制度、规范、操作手册、技术文档等非结构化内容）\n\n"
            "返回格式（严格 JSON，不要多余内容）：\n"
            '{{"intent": "casual_chat|data_query|doc_search", "confidence": 0.0~1.0, "reason": "简短理由"}}'
        ),
    ),
    ("human", "{question}"),
])


class IntentService:
    """LLM-based intent classifier for the three-route chat pipeline."""

    def __init__(self):
        self._model: ChatOpenAI | None = None

    def _get_model(self) -> ChatOpenAI | None:
        if not (settings.EFFECTIVE_LLM_BASE_URL and settings.EFFECTIVE_LLM_API_KEY and settings.EFFECTIVE_LLM_MODEL):
            return None
        if self._model is None:
            self._model = ChatOpenAI(
                base_url=settings.EFFECTIVE_LLM_BASE_URL.rstrip("/"),
                api_key=settings.EFFECTIVE_LLM_API_KEY,
                model=settings.EFFECTIVE_LLM_MODEL,
                temperature=0.0,
                request_timeout=30,
            )
        return self._model

    def classify(self, question: str) -> tuple[str, float, str]:
        """
        对用户问题做意图分类。

        Returns:
            (intent, confidence, reason)
        """
        model = self._get_model()
        if model is None:
            # LLM 未配置时，降级为文档检索
            return INTENT_DOC_SEARCH, 0.5, "LLM未配置，默认走文档检索"

        # 如果 Text2SQL 未启用，提示词中隐藏 data_query 选项
        data_query_hint = ""
        if not settings.TEXT2SQL_ENABLED:
            data_query_hint = "（当前未启用，不要选此项）"

        chain = _CLASSIFY_PROMPT | model | StrOutputParser()
        try:
            raw = chain.invoke({
                "question": question,
                "data_query_hint": data_query_hint,
            })
            result = self._parse_result(raw)
            logger.info(f"Intent classified: question='{question[:50]}...' → {result[0]} ({result[1]:.2f})")
            return result
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}, falling back to doc_search")
            return INTENT_DOC_SEARCH, 0.5, f"分类失败: {e}"

    @staticmethod
    def _parse_result(raw: str) -> tuple[str, float, str]:
        """Parse the JSON response from the LLM."""
        # 尝试提取 JSON（LLM 可能在前后加文字）
        text = raw.strip()
        # 找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]

        data = json.loads(text)
        intent = data.get("intent", INTENT_DOC_SEARCH)
        confidence = float(data.get("confidence", 0.5))
        reason = data.get("reason", "")

        if intent not in ALL_INTENTS:
            intent = INTENT_DOC_SEARCH
        return intent, confidence, reason


intent_service = IntentService()
