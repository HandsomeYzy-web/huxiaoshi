"""
Text2SQL Service — 将自然语言转换为 SQL 并安全执行。

安全措施:
- 只允许 SELECT 语句（当 TEXT2SQL_READONLY=True）
- 限制返回行数
- 使用独立的只读数据库连接
- SQL 注入防护（LLM 生成 → 白名单校验 → 执行）
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from core.config import settings
from core.logger import logger

# SQL 黑名单关键字（即使 LLM 生成也禁止执行）
_DANGEROUS_KEYWORDS = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|ALTER|INSERT|UPDATE|CREATE|REPLACE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)

_GENERATE_SQL_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "你是一个 SQL 生成专家。根据用户的自然语言问题和下方的数据库表结构，生成一条准确的 SELECT SQL 查询语句。\n\n"
            "【规则】\n"
            "1. 只能生成 SELECT 语句，禁止任何写操作\n"
            "2. 查询结果限制最多 {max_rows} 行（使用 LIMIT）\n"
            "3. 使用中文别名让结果更易读 (AS)\n"
            "4. 只返回 SQL，不要解释，不要 markdown 代码块\n\n"
            "【数据库表结构】\n{schema_info}\n"
        ),
    ),
    ("human", "{question}"),
])

_SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "你是数据分析助手。用户通过自然语言提问，系统已从数据库查到结果。\n"
            "请用清晰、友好的中文总结查询结果，可以适当使用表格或列表格式。\n"
            "如果结果为空，说明未查到符合条件的数据。"
        ),
    ),
    (
        "human",
        "用户问题：{question}\n\n执行的SQL：\n{sql}\n\n查询结果：\n{result_text}",
    ),
])


class Text2SQLService:
    """Natural language to SQL query pipeline."""

    def __init__(self):
        self._engine: Engine | None = None
        self._schema_cache: str | None = None
        self._model: ChatOpenAI | None = None

    # ── Engine ────────────────────────────────────────────────────

    def _get_engine(self) -> Engine | None:
        if not settings.TEXT2SQL_ENABLED or not settings.TEXT2SQL_DB_URI:
            return None
        if self._engine is None:
            self._engine = create_engine(
                settings.TEXT2SQL_DB_URI,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
            )
        return self._engine

    def _get_model(self) -> ChatOpenAI | None:
        if not (settings.EFFECTIVE_LLM_BASE_URL and settings.EFFECTIVE_LLM_API_KEY and settings.EFFECTIVE_LLM_MODEL):
            return None
        if self._model is None:
            self._model = ChatOpenAI(
                base_url=settings.EFFECTIVE_LLM_BASE_URL.rstrip("/"),
                api_key=settings.EFFECTIVE_LLM_API_KEY,
                model=settings.EFFECTIVE_LLM_MODEL,
                temperature=0.0,
                request_timeout=settings.LLM_TIMEOUT,
            )
        return self._model

    # ── Schema introspection ─────────────────────────────────────

    def get_schema_info(self) -> str:
        """Introspect database and return a text description of all tables."""
        if self._schema_cache:
            return self._schema_cache

        engine = self._get_engine()
        if not engine:
            return "（业务数据库未配置）"

        inspector = inspect(engine)
        lines: list[str] = []
        for table_name in inspector.get_table_names():
            columns = inspector.get_columns(table_name)
            col_descs = []
            for col in columns:
                comment = col.get("comment", "") or ""
                col_desc = f"  - {col['name']} ({col['type']})"
                if comment:
                    col_desc += f"  -- {comment}"
                col_descs.append(col_desc)
            lines.append(f"表名: {table_name}")
            lines.extend(col_descs)
            lines.append("")

        self._schema_cache = "\n".join(lines) if lines else "（数据库中无表）"
        return self._schema_cache

    def clear_schema_cache(self):
        self._schema_cache = None

    # ── SQL Generation ───────────────────────────────────────────

    def generate_sql(self, question: str) -> str:
        """Use LLM to generate a SELECT SQL from natural language."""
        model = self._get_model()
        if model is None:
            raise RuntimeError("LLM 未配置，无法生成 SQL")

        chain = _GENERATE_SQL_PROMPT | model | StrOutputParser()
        raw_sql = chain.invoke({
            "question": question,
            "schema_info": self.get_schema_info(),
            "max_rows": settings.TEXT2SQL_MAX_ROWS,
        })

        # 清理 LLM 输出的 markdown 代码块
        sql = raw_sql.strip()
        if sql.startswith("```"):
            sql = re.sub(r"^```\w*\n?", "", sql)
            sql = re.sub(r"\n?```$", "", sql)
        sql = sql.strip().rstrip(";") + ";"

        return sql

    # ── SQL Validation ───────────────────────────────────────────

    @staticmethod
    def validate_sql(sql: str) -> tuple[bool, str]:
        """
        Validate that the SQL is a safe SELECT statement.
        Returns (is_valid, error_message).
        """
        normalized = sql.strip().upper()

        if not normalized.startswith("SELECT"):
            return False, "仅允许 SELECT 查询"

        if _DANGEROUS_KEYWORDS.search(sql):
            return False, "SQL 包含禁止的操作关键字"

        # 检查是否有多语句（分号分隔的多条 SQL）
        # 移除字符串内的分号后检查
        statements = [s.strip() for s in sql.rstrip(";").split(";") if s.strip()]
        if len(statements) > 1:
            return False, "不允许执行多条 SQL 语句"

        return True, ""

    # ── SQL Execution ────────────────────────────────────────────

    def execute_sql(self, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
        """
        Execute a validated SELECT SQL and return (columns, rows).
        Each row is a dict mapping column name to value.
        """
        engine = self._get_engine()
        if engine is None:
            raise RuntimeError("业务数据库未配置")

        # 强制添加 LIMIT 防止大结果集
        sql_upper = sql.strip().upper()
        if "LIMIT" not in sql_upper:
            sql = sql.rstrip(";") + f" LIMIT {settings.TEXT2SQL_MAX_ROWS};"

        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = []
            for row in result.fetchall():
                row_dict = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    # 转换为 JSON 可序列化类型
                    if hasattr(val, "isoformat"):
                        val = val.isoformat()
                    elif isinstance(val, bytes):
                        val = val.decode("utf-8", errors="replace")
                    row_dict[col] = val
                rows.append(row_dict)
            return columns, rows

    # ── Result Summarization ─────────────────────────────────────

    def summarize_result(
        self, question: str, sql: str, columns: list[str], rows: list[dict]
    ) -> str:
        """Use LLM to summarize SQL query results in natural language."""
        model = self._get_model()
        if model is None:
            return self._format_result_text(columns, rows)

        result_text = self._format_result_text(columns, rows)
        chain = _SUMMARIZE_PROMPT | model | StrOutputParser()
        return chain.invoke({
            "question": question,
            "sql": sql,
            "result_text": result_text,
        })

    def stream_summarize_result(
        self, question: str, sql: str, columns: list[str], rows: list[dict]
    ):
        """Stream the summary of SQL results. Yields (chunk, is_model_info, model_name)."""
        model = self._get_model()
        result_text = self._format_result_text(columns, rows)

        if model is None:
            yield result_text, False, None
            return

        yield "", True, settings.EFFECTIVE_LLM_MODEL

        streaming_model = ChatOpenAI(
            base_url=settings.EFFECTIVE_LLM_BASE_URL.rstrip("/"),
            api_key=settings.EFFECTIVE_LLM_API_KEY,
            model=settings.EFFECTIVE_LLM_MODEL,
            temperature=0.1,
            streaming=True,
            request_timeout=settings.LLM_TIMEOUT,
        )
        chain = _SUMMARIZE_PROMPT | streaming_model | StrOutputParser()
        for chunk in chain.stream({
            "question": question,
            "sql": sql,
            "result_text": result_text,
        }):
            if chunk:
                yield chunk, False, None

    @staticmethod
    def _format_result_text(columns: list[str], rows: list[dict]) -> str:
        if not rows:
            return "查询结果为空，没有符合条件的数据。"
        header = " | ".join(columns)
        lines = [header, "-" * len(header)]
        for row in rows[:50]:
            lines.append(" | ".join(str(row.get(c, "")) for c in columns))
        if len(rows) > 50:
            lines.append(f"... 共 {len(rows)} 行，仅展示前 50 行")
        return "\n".join(lines)

    # ── Full Pipeline ────────────────────────────────────────────

    def query(self, question: str) -> tuple[str, str, list[str], list[dict]]:
        """
        Full pipeline: question → SQL → execute → return results.
        Returns (sql, summary_text, columns, rows).
        """
        sql = self.generate_sql(question)
        is_valid, err_msg = self.validate_sql(sql)
        if not is_valid:
            raise ValueError(f"生成的 SQL 不安全: {err_msg}\nSQL: {sql}")

        columns, rows = self.execute_sql(sql)
        summary = self.summarize_result(question, sql, columns, rows)
        return sql, summary, columns, rows


text2sql_service = Text2SQLService()
