"""Text2SQL SQL 自动修复服务。

当生成的 SQL 校验/执行失败时，把「失败 SQL + 错误原因 + 真实表结构」回灌给大模型，
按字段不存在、类型不匹配、语法错误、GROUP BY 不合规等常见错误给出修复策略，
重新生成一条更可能执行成功的 SELECT。由 facade 在修复循环中反复调用。
"""

from __future__ import annotations

import re
from typing import Any, Callable

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from services.text2sql.schema_service import Text2SQLSchemaService

_REPAIR_SQL_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "你是 SQL 修复器，请根据失败原因修复 SQL。\n\n"
            "修复策略：\n"
            "- 若错误是「字段不存在」：在 schema_json 中找最接近的字段名替换。\n"
            "- 若错误是「数据类型不匹配」：检查字段类型，调整条件值格式。\n"
            "- 若错误是「语法错误」：修复 SQL 语法，保持原始查询意图。\n\n"
            "- 若错误是「GROUP BY 校验失败」：将未聚合字段加入 GROUP BY，或改写为聚合函数。\n\n"
            "硬性规则：\n"
            "1. 只能输出一条 SELECT 语句。\n"
            "2. 表名和字段必须来自 schema_json。\n"
            "3. 严禁使用 UNION 和多语句。\n"
            "4. 注意字段的数据类型和注释信息。\n"
            "5. 仅输出 SQL 本身，不要解释，不要 markdown。\n"
            "6. 严禁使用表别名（例如 a、t1、l、x），所有字段必须使用完整表名.字段名。\n\n"
            "多轮对话历史（用于理解指代和延续上一问，若与当前问题无关可忽略）：\n{conversation_context}\n\n"
            "关系约束模式：\n{relation_mode_instructions}\n\n"
            "可用关系白名单（仅在多表模式下可用）：\n{relation_hints_text}\n\n"
            "允许查询的表：\n{allowed_tables_text}\n\n"
            "真实数据库结构（JSON）：\n{schema_json}\n\n"
            "额外业务约束：\n{prompt_hint}\n"
        ),
    ),
    (
        "human",
        "用户问题：{question}\n\n"
        "失败 SQL：\n{failed_sql}\n\n"
        "错误原因：{error_message}\n",
    ),
])

class Text2SQLRepairService:
    """在 SQL 校验失败时按错误信息自动修复 SQL。"""
    def __init__(
        self,
        model_provider: Callable[[], ChatOpenAI | None],
        schema_service: Text2SQLSchemaService,
        ensure_limit: Callable[[str], str],
    ):
        """注入模型提供器、Schema 服务和 LIMIT 规范器。"""
        self._model_provider = model_provider
        self._schema_service = schema_service
        self._ensure_limit = ensure_limit

    @staticmethod
    def _build_allowed_tables_text(selected_tables: list[str]) -> str:
        """把候选表列表格式化为提示词片段。"""
        if not selected_tables:
            return "（未指定；可从 schema_json 中选择一张表）"
        return "\n".join(f"- {table_name}" for table_name in selected_tables)

    @staticmethod
    def _build_relation_prompt_context(relation_hints: list[dict]) -> tuple[str, str]:
        """根据关系白名单生成（关系约束说明, 关系白名单文本），约束修复时的 JOIN 行为。"""
        if not relation_hints:
            return (
                "当前为单表模式：你必须只使用一张表，禁止使用 JOIN。",
                "（无）",
            )
        lines: list[str] = []
        for relation in relation_hints:
            source_table = str(relation.get("source_table") or "").strip()
            target_table = str(relation.get("target_table") or "").strip()
            source_columns = [str(item).strip() for item in (relation.get("source_columns") or []) if str(item).strip()]
            target_columns = [str(item).strip() for item in (relation.get("target_columns") or []) if str(item).strip()]
            if not source_table or not target_table or not source_columns or len(source_columns) != len(target_columns):
                continue
            pairs = [f"{source_table}.{left} = {target_table}.{right}" for left, right in zip(source_columns, target_columns)]
            relation_type = str(relation.get("relation_type") or "").strip()
            description = str(relation.get("description") or "").strip()
            suffix_parts = []
            if relation_type:
                suffix_parts.append(f"类型: {relation_type}")
            if description:
                suffix_parts.append(f"说明: {description}")
            suffix = f"（{'；'.join(suffix_parts)}）" if suffix_parts else ""
            lines.append(f"- {' AND '.join(pairs)}{suffix}")
        if not lines:
            return (
                "当前为单表模式：你必须只使用一张表，禁止使用 JOIN。",
                "（无）",
            )
        return (
            "当前为多表按需模式：如需 JOIN，仅可使用白名单关系，禁止猜测未提供的关系。",
            "\n".join(lines),
        )

    def repair_sql(
        self,
        *,
        db: Session,
        question: str,
        failed_sql: str,
        error_message: str,
        runtime_config: dict[str, Any],
    ) -> str:
        """结合错误信息和 Schema 重新生成更可执行的 SQL。"""
        model = self._model_provider()
        if model is None:
            # 模型不可用时无法修复，原样返回失败 SQL（仅补 LIMIT），由上层校验决定去留。
            return self._ensure_limit(failed_sql)
        selected_tables = runtime_config.get("selected_tables") or []
        relation_hints = runtime_config.get("relation_hints") or []
        queryable_columns_map = runtime_config.get("queryable_columns_map")
        schema_json = self._schema_service.build_live_schema_json(
            db,
            selected_tables or None,
            queryable_columns_map=queryable_columns_map,
        )
        allowed_tables_text = self._build_allowed_tables_text(selected_tables)
        relation_mode_instructions, relation_hints_text = self._build_relation_prompt_context(relation_hints)
        prompt_hint = runtime_config.get("prompt_hint") or "（无）"
        conversation_context = runtime_config.get("conversation_context") or "（无）"
        chain = _REPAIR_SQL_PROMPT | model | StrOutputParser()
        repaired_sql = chain.invoke(
            {
                "question": question,
                "failed_sql": failed_sql,
                "error_message": error_message,
                "allowed_tables_text": allowed_tables_text,
                "relation_mode_instructions": relation_mode_instructions,
                "relation_hints_text": relation_hints_text,
                "schema_json": schema_json,
                "prompt_hint": prompt_hint,
                "conversation_context": conversation_context,
            }
        )
        return self._ensure_limit(self._normalize_sql_output(repaired_sql))

    @staticmethod
    def _normalize_sql_output(raw_sql: str) -> str:
        """清理模型输出，去掉代码块包裹。"""
        sql = raw_sql.strip()
        if sql.startswith("```"):
            sql = re.sub(r"^```\w*\n?", "", sql)
            sql = re.sub(r"\n?```$", "", sql)
        return sql.strip()

