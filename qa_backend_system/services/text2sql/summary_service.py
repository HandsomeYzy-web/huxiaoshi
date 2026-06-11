"""Text2SQL 结果摘要服务。

把执行得到的结果集（列 + 行）连同原始问题与 SQL 交给大模型，生成清晰友好的中文回答，
支持一次性与流式两种输出；模型不可用或流式失败时，降级为基于行列统计的兜底文案，
保证「即使没有大模型也能给用户一个可读的结果说明」。
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, Callable

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

_SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是数据分析助手。用户通过自然语言提问，系统已从数据库查到结果。\n"
        "请用清晰、友好的中文总结查询结果，可以适当使用表格或列表格式。\n"
        "如果结果为空，说明未查到符合条件的数据。",
    ),
    ("human", "用户问题：{question}\n\n执行的SQL：\n{sql}\n\n查询结果：\n{result_text}"),
])

class Text2SQLSummaryService:
    """把 SQL 结果整理成面向用户的自然语言总结。"""
    def __init__(
        self,
        model_provider: Callable[[], ChatOpenAI | None],
        streaming_model_provider: Callable[[], ChatOpenAI | None] | None = None,
    ):
        """注入模型提供器。"""
        self._model_provider = model_provider
        self._streaming_model_provider = streaming_model_provider or model_provider

    def summarize_result(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> str:
        """生成查询结果摘要；模型不可用时使用兜底文案。"""
        model = self._model_provider()
        if model is None:
            return self.build_fallback_summary(columns, rows)
        result_text = self.format_result_text(columns, rows)
        chain = _SUMMARIZE_PROMPT | model | StrOutputParser()
        return chain.invoke(
            {
                "question": question,
                "sql": sql,
                "result_text": result_text,
            }
        )

    def stream_summarize_result(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> Generator[str, None, None]:
        """流式生成查询结果摘要；失败时降级为一次性摘要。"""
        model = self._streaming_model_provider()
        if model is None:
            yield self.build_fallback_summary(columns, rows)
            return

        result_text = self.format_result_text(columns, rows)
        chain = _SUMMARIZE_PROMPT | model | StrOutputParser()
        has_content = False

        try:
            for chunk in chain.stream(
                {
                    "question": question,
                    "sql": sql,
                    "result_text": result_text,
                }
            ):
                if chunk:
                    has_content = True
                    yield chunk
        except Exception:  # noqa: BLE001
            has_content = False

        if not has_content:
            try:
                yield self.summarize_result(question, sql, columns, rows)
            except Exception:  # noqa: BLE001
                yield self.build_fallback_summary(columns, rows)

    @staticmethod
    def build_fallback_summary(columns: list[str], rows: list[dict[str, Any]]) -> str:
        """在无模型场景下生成简明中文摘要。"""
        if not rows:
            return "未查到符合条件的数据。"
        total_rows = len(rows)
        total_columns = len(columns)
        if total_rows == 1 and total_columns == 1:
            only_column = columns[0]
            return f"查询完成，共 1 条结果：{only_column} = {rows[0].get(only_column, '')}"
        visible_columns = "、".join(columns[:6])
        if total_columns > 6:
            visible_columns += " 等"
        return (
            f"查询完成，共返回 {total_rows} 行、{total_columns} 列。"
            f"字段包括：{visible_columns}。"
            "下方表格可查看明细数据。"
        )

    @staticmethod
    def format_result_text(columns: list[str], rows: list[dict[str, Any]]) -> str:
        """把结果集格式化成适合喂给模型的文本。"""
        if not rows:
            return "查询结果为空，没有符合条件的数据。"
        header = " | ".join(columns)
        lines = [header, "-" * len(header)]
        for row in rows[:50]:
            lines.append(" | ".join(str(row.get(column, "")) for column in columns))
        if len(rows) > 50:
            lines.append(f"... 共 {len(rows)} 行，仅展示前 50 行")
        return "\n".join(lines)
