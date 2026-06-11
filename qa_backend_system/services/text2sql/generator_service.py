"""Text2SQL SQL 生成服务。

负责把「自然语言问题 + 实时表结构 + 业务约束 + 关系白名单 + few-shot 样例 + 多轮上下文」
组装进提示词，调用大模型生成「单条 SELECT」SQL，并对模型输出做清洗（去 markdown、补分号）。
提示词中的硬性规则约束了模型行为：禁止臆造表/字段、禁止 UNION/多语句、禁止表别名、
优先参考字段注释选字段等，从源头降低生成出错与越权的概率。
"""

from __future__ import annotations

import re
from typing import Any, Callable

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from services.text2sql.schema_service import Text2SQLSchemaService

_GENERATE_SQL_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "你是学校数据查询助手，负责将自然语言问题转换为 SQL 查询。\n\n"
            "硬性规则：\n"
            "1. 只能输出一条 SELECT 语句。\n"
            "2. 表名和字段必须来自 schema_json，禁止臆造。\n"
            "3. 严禁使用 UNION 和多语句。\n"
            "4. 当问题信息不足时，优先忽略无法确认的条件，不要猜字段。\n"
            "5. 明细查询建议补 LIMIT；统计聚合查询（如 COUNT/SUM/AVG）可不加 LIMIT。\n"
            "6. 仅输出 SQL 本身，不要解释，不要 markdown。\n"
            "7. 若用户问“有哪些/列表/明细”，优先返回可读的关键字段，不要只返回单个编码类字段。\n"
            "8. 字段注释（comment）描述了字段业务含义，请优先参考注释选择字段和条件值。\n"
            "9. 注意字段类型：TINYINT 条件值用数字，VARCHAR 条件值用字符串。\n"
            "10. 严禁使用表别名（例如 a、t1、l、x），所有字段必须使用完整表名.字段名。\n\n"
            "多轮对话历史（用于理解指代和延续上一问，若与当前问题无关可忽略）：\n{conversation_context}\n\n"
            "关系约束模式：\n{relation_mode_instructions}\n\n"
            "可用关系白名单（仅在多表模式下可用）：\n{relation_hints_text}\n\n"
            "允许查询的表：\n{allowed_tables_text}\n\n"
            "真实数据库结构（JSON）：\n{schema_json}\n\n"
            "额外业务约束：\n{prompt_hint}\n\n"
            "相似问题参考（仅供参考，不可直接复用）：\n{few_shot_examples}\n"
        ),
    ),
    ("human", "用户问题：{question}"),
])

class Text2SQLGeneratorService:
    """根据问题与实时 Schema 生成可执行 SQL。"""
    def __init__(
        self,
        model_provider: Callable[[], ChatOpenAI | None],
        schema_service: Text2SQLSchemaService,
    ):
        """注入模型提供器和 Schema 服务。"""
        self._model_provider = model_provider
        self._schema_service = schema_service

    @staticmethod
    def _build_allowed_tables_text(selected_tables: list[str]) -> str:
        """把候选表列表格式化为提示词片段。"""
        if not selected_tables:
            return "（未指定；可从 schema_json 中选择一张表）"
        return "\n".join(f"- {table_name}" for table_name in selected_tables)

    @staticmethod
    def _build_relation_prompt_context(relation_hints: list[dict]) -> tuple[str, str]:
        """根据关系白名单生成（关系约束说明, 关系白名单文本）二元组。

        无关系提示 → 单表模式（禁止 JOIN）；有合法关系 → 多表按需模式，
        并把每条关系格式化为「源表.列 = 目标表.列」的可读约束，供模型按白名单 JOIN。
        """
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
            (
                "当前为多表按需模式：若单表可回答，优先单表。"
                "如需 JOIN，仅可使用上面白名单中的字段对应关系，禁止猜测未提供关系。"
            ),
            "\n".join(lines),
        )

    def generate_sql(
        self,
        *,
        db: Session,
        question: str,
        runtime_config: dict[str, Any],
    ) -> str:
        """基于问题、候选表和 Schema 生成 SQL。"""
        selected_tables = runtime_config.get("selected_tables") or []
        prompt_hint = runtime_config.get("prompt_hint") or "（无）"
        conversation_context = runtime_config.get("conversation_context") or "（无）"
        few_shot_examples = runtime_config.get("few_shot_examples") or "（暂无历史参考）"
        relation_hints = runtime_config.get("relation_hints") or []
        queryable_columns_map = runtime_config.get("queryable_columns_map")
        if not selected_tables:
            raise ValueError("未选择可查询的表，无法生成 SQL")
        model = self._model_provider()
        if model is None:
            raise ValueError("大模型不可用")
        schema_json = self._schema_service.build_live_schema_json(
            db,
            selected_tables,
            queryable_columns_map=queryable_columns_map,
            question=question,
        )
        relation_mode_instructions, relation_hints_text = self._build_relation_prompt_context(relation_hints)
        chain = _GENERATE_SQL_PROMPT | model | StrOutputParser()
        raw_sql = chain.invoke(
            {
                "question": question,
                "schema_json": schema_json,
                "allowed_tables_text": self._build_allowed_tables_text(selected_tables),
                "relation_mode_instructions": relation_mode_instructions,
                "relation_hints_text": relation_hints_text,
                "prompt_hint": prompt_hint,
                "conversation_context": conversation_context,
                "few_shot_examples": few_shot_examples,
            }
        )
        return self._normalize_sql_output(raw_sql)

    @staticmethod
    def _normalize_sql_output(raw_sql: str) -> str:
        """清理模型输出，只保留单条 SQL 文本。"""
        sql = raw_sql.strip()
        if sql.startswith("```"):
            sql = re.sub(r"^```\w*\n?", "", sql)
            sql = re.sub(r"\n?```$", "", sql)
        return sql.strip().rstrip(";") + ";"

