"""Text2SQL 核心业务编排服务（Facade 门面）。

本模块是「自然语言转 SQL」全链路的总调度入口，对上层 router 暴露 query / debug_generate
两个能力，对下编排各子服务，串成一条完整流水线：

    1. 表路由（_route_tables）   ：知识库向量召回 + 关键词/画像打分 + 关系图扩展 + LLM 决策，
                                   从用户「可查询」的表中挑出回答问题所需的最小表集合。
    2. SQL 生成（generator）     ：结合候选表 schema、字段权限、枚举提示、few-shot 历史样例、
                                   多轮对话上下文，调用大模型生成 SQL。
    3. 校验（validator）         ：白名单表/字段、JOIN 关系白名单、最大表数等安全与合规校验。
    4. 自动修复（repair）        ：校验不通过时把错误信息回灌给大模型迭代修复，最多 N 轮。
    5. 执行（executor）          ：在目标业务库执行 SQL，执行前自动补 LIMIT、剥离别名、展开 SELECT *。
    6. 结果摘要（summary）       ：把结果集交给大模型生成自然语言回答（支持流式）。
    7. 日志（log）               ：记录成功/失败查询，供审计与 few-shot 样例回流。

可选增强能力（按配置开关惰性加载，关闭时退化为 _Noop* 空实现，主流程无感知）：
    - 向量路由（vector_service）     ：仅检索专用「table_desc」知识库做语义召回
      （TABLE_ROUTE_KB_ID 优先，TEXT2SQL_TABLE_DESC_KB_NAME 名称兜底）。
    - few-shot 样例（few_shot）      ：召回历史高分查询作为提示样例。
    - 枚举值提示（enum_hint）        ：把字段的枚举取值喂给模型，减少字面量写错导致的空结果。
    - self-consistency 投票          ：同一问题多温度采样多份 SQL，按执行结果签名投票取多数，提升稳定性。
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlglot import exp, parse_one
from sqlalchemy.orm import Session

from core.config import settings
from services.text2sql.config_service import Text2SQLConfigService
from services.text2sql.connection_service import Text2SQLConnectionService
from services.text2sql.executor_service import Text2SQLExecutorService
from services.text2sql.field_permission_service import Text2SQLFieldPermissionService
from services.text2sql.generator_service import Text2SQLGeneratorService
from services.text2sql.log_service import Text2SQLLogService
from services.text2sql.repair_service import Text2SQLRepairService
from services.text2sql.relation_service import Text2SQLRelationService
from services.text2sql.schema_service import Text2SQLSchemaService
from services.text2sql.summary_service import Text2SQLSummaryService
from services.text2sql.text_tokens import build_search_tokens, contains_chinese
from services.text2sql.validator_service import Text2SQLValidatorService

# 以下 _Noop* 为「空实现」降级方案：当对应增强能力被配置关闭、或初始化失败时，
# facade 注入这些占位实现，保证主流程不感知差异、照常运行（只是少了该项增强）。
class _NoopEnumHintService:
    """枚举提示降级实现：原样返回 prompt_hint，不附加任何枚举信息。"""

    def build_prompt_hint(self, **kwargs):
        return str(kwargs.get("base_prompt_hint") or "")


class _NoopFewShotService:
    """few-shot 降级实现：始终返回「无历史样例」。"""

    def search_similar_examples(self, *args, **kwargs):
        return "(no historical examples)"


class _NoopVectorService:
    """向量召回降级实现：返回空分数，表路由退化为纯关键词/画像打分。"""

    def search_tables(self, *args, **kwargs):
        return {}

_console_logger = logging.getLogger("text2sql.console")
if not _console_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    _console_logger.addHandler(_handler)
_console_logger.setLevel(logging.INFO)
_console_logger.propagate = False

# 单表路由提示词：让模型从候选表中只挑「一张」主表（多表开关关闭时使用）。
_TABLE_SELECTION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are a database table selector.\n"
            "Choose exactly one primary table from the candidates.\n"
            "Prefer business-semantic match first, then field-level match.\n"
            "Output only the table name, without markdown or explanation.\n\n"
            "Candidate tables:\n{candidates_info}\n"
        ),
    ),
    ("human", "Question: {question}"),
])

# 多表路由提示词：让模型在候选表 + JOIN 关系白名单约束下，挑出回答问题所需的最小表集合，
# 并严格输出 JSON（多表开关开启时使用）。
_ROUTER_TABLE_SELECTION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are a Text2SQL Router Agent.\n"
            "Task: choose the minimum required table set for answering the question.\n\n"
            "Rules:\n"
            "1. You may only select from candidate tables below.\n"
            "2. For JOIN, only use relations listed in the whitelist.\n"
            "3. If one table is enough, return one table.\n"
            "4. If multiple tables are required, include necessary bridge tables.\n"
            "5. Never invent table names or relations.\n"
            "6. Output strict JSON only: {{\"tables\": [\"table_a\", \"table_b\"]}}.\n\n"
            "Candidate tables with columns:\n{candidates_info}\n\n"
            "JOIN whitelist:\n{relation_hints_text}\n"
        ),
    ),
    ("human", "Question: {question}"),
])

class Text2SQLClarificationNeeded(ValueError):
    """路由信号不足、需要用户补充澄清时抛出（由 query() 捕获并转为澄清回复）。"""

    def __init__(self, clarify_question: str):
        self.clarify_question = str(clarify_question or "").strip() or "请补充更具体的查询条件或业务实体。"
        super().__init__(self.clarify_question)


@dataclass
class SQLAttemptResult:
    """单次「生成 + 校验 + 修复」尝试的结果快照。"""

    generated_sql: str  # 模型首次生成的原始 SQL（未经修复）
    final_sql: str  # 经别名剥离 / SELECT * 展开 / 补 LIMIT / 修复后的最终 SQL
    is_valid: bool  # 最终 SQL 是否通过校验
    validation_message: str  # 校验信息（失败时为失败原因）
    repair_attempts: int  # 实际触发的自动修复轮数（0 表示一次通过）
    candidate_columns_map: dict[str, set[str]]  # 本次候选表的可查询字段映射（已限定在权限范围内）


ProgressCallback = Callable[[str, dict], None]

class Text2SQLFacadeService:
    """Text2SQL 流水线总编排器：路由 → 生成 → 校验 → 修复 → 执行 → 摘要。

    通过依赖注入持有各子服务，自身只负责「编排」与「跨服务的业务决策」，
    例如多表关系守卫、self-consistency 投票、空结果二次探测等。
    """

    def __init__(
        self,
        *,
        connection_service: Text2SQLConnectionService,
        schema_service: Text2SQLSchemaService,
        config_service: Text2SQLConfigService,
        field_permission_service: Text2SQLFieldPermissionService,
        relation_service: Text2SQLRelationService,
        log_service: Text2SQLLogService,
    ) -> None:
        """初始化并装配所有子服务依赖。

        外部注入的服务（连接/schema/配置/字段权限/关系/日志）由 __init__.py 统一构建并复用；
        内部新建的服务（校验/生成/修复/执行/摘要）由本类自行持有；
        增强类服务（向量/few-shot/枚举提示）按配置开关惰性构建，关闭时为 _Noop* 空实现。
        """
        # —— 外部注入的基础服务（跨模块共享单例）——
        self.connection_service = connection_service  # 业务库连接（取 engine、密文解密）
        self.schema_service = schema_service  # 表结构 / 字段 / 表注释元数据
        self.config_service = config_service  # 用户在某连接下选了哪些表、自定义 prompt
        self.field_permission_service = field_permission_service  # 表级 / 字段级查询权限
        self.relation_service = relation_service  # 表间 JOIN 关系白名单
        self.log_service = log_service  # 查询日志读写
        # —— 本类自建的流水线服务 ——
        self.validator_service = Text2SQLValidatorService()  # SQL 安全/合规校验
        self.generator_service = Text2SQLGeneratorService(self._get_model, schema_service)  # SQL 生成
        self.repair_service = Text2SQLRepairService(self._get_model, schema_service, self._ensure_limit)  # 自动修复
        self.executor_service = Text2SQLExecutorService(
            self.connection_service.get_engine,
            self._ensure_limit,
            getattr(self.connection_service, "get_active_db_type", None),
        )  # SQL 执行（按连接库类型在执行前转写方言）
        self.summary_service = Text2SQLSummaryService(self._get_model, self._get_streaming_model)  # 结果摘要
        # —— 增强能力（按开关惰性加载，未开启时降级为 _Noop* 实现）——
        self.vector_service = self._build_vector_service()  # 知识库语义召回
        self.few_shot_service = self._build_few_shot_service()  # 历史高分查询样例
        self.enum_hint_service = self._build_enum_hint_service()  # 字段枚举值提示
        self._model: ChatOpenAI | None = None
        self._model_key = ""
        self._streaming_model: ChatOpenAI | None = None
        self._streaming_model_key = ""
        # 当前 LLM 采样温度，由 _run_with_temperature 临时切换（用于 self-consistency 多候选采样）。
        self._current_temperature: float = 0.0

    @staticmethod
    def _resolve_user_id(user_id: int | None) -> int:
        return max(1, int(user_id or 1))

    @staticmethod
    def _is_few_shot_enabled() -> bool:
        """是否启用 few-shot 历史样例增强。"""
        return bool(getattr(settings, "TEXT2SQL_FEW_SHOT_ENABLED", False))

    @staticmethod
    def _is_vector_route_enabled() -> bool:
        """是否启用向量路由：配置了路由知识库 ID，或配置了 table_desc 知识库名称（按名称解析）。"""
        if int(getattr(settings, "TABLE_ROUTE_KB_ID", 0) or 0) > 0:
            return True
        return bool(str(getattr(settings, "TEXT2SQL_TABLE_DESC_KB_NAME", "")).strip())

    def _build_enum_hint_service(self):
        if not bool(getattr(settings, "TEXT2SQL_ENUM_HINT_ENABLED", False)):
            return _NoopEnumHintService()
        try:
            from services.text2sql.enum_hint_service import Text2SQLEnumHintService

            return Text2SQLEnumHintService(
                self.connection_service.get_engine,
                self.schema_service,
                getattr(self.connection_service, "get_active_db_type", None),
            )
        except Exception:  # noqa: BLE001
            _console_logger.exception("enum hint service init failed, falling back to noop")
            return _NoopEnumHintService()

    def _build_few_shot_service(self):
        if not self._is_few_shot_enabled():
            return _NoopFewShotService()
        try:
            from services.text2sql.few_shot_service import Text2SQLFewShotService

            return Text2SQLFewShotService(max_examples=3, candidate_limit=200)
        except Exception:  # noqa: BLE001
            _console_logger.exception("few-shot service init failed, falling back to noop")
            return _NoopFewShotService()

    def _build_vector_service(self):
        if not self._is_vector_route_enabled():
            return _NoopVectorService()
        try:
            from services.text2sql.vector_service import Text2SQLVectorService

            return Text2SQLVectorService(kb_id=int(settings.TABLE_ROUTE_KB_ID or 0))
        except Exception:  # noqa: BLE001
            _console_logger.exception("vector service init failed, falling back to noop")
            return _NoopVectorService()

    # 下面三个方法是对「字段权限 / 关系」服务的薄封装：统一带上 user_id 过滤，
    # 并用 try/except TypeError 兼容旧签名（便于测试 mock 替换为不带 user_id 的实现）。
    def _queryable_table_names(
        self,
        db: Session,
        table_names: list[str] | None,
        user_id: int,
    ) -> list[str]:
        """返回当前用户在权限范围内「可查询」的表名（按表级权限过滤）。"""
        try:
            return self.field_permission_service.get_queryable_table_names(
                db,
                table_names,
                user_id=user_id,
            )
        except TypeError:
            return self.field_permission_service.get_queryable_table_names(db, table_names)

    def _queryable_columns_map(
        self,
        db: Session,
        table_names: list[str] | None,
        user_id: int,
    ) -> dict[str, set[str]]:
        """返回 {表名: 可查询字段集合}，字段已按字段级权限过滤。"""
        try:
            return self.field_permission_service.get_queryable_columns_map(
                db,
                table_names,
                user_id=user_id,
            )
        except TypeError:
            return self.field_permission_service.get_queryable_columns_map(db, table_names)

    def _active_relations(
        self,
        db: Session,
        table_names: list[str],
        user_id: int,
    ) -> list[dict]:
        """返回给定表集合之间「已启用」的 JOIN 关系（多表查询的 JOIN 白名单来源）。"""
        try:
            return self.relation_service.get_active_relations_by_tables(
                db,
                table_names,
                user_id=user_id,
            )
        except TypeError:
            return self.relation_service.get_active_relations_by_tables(db, table_names)

    def _route_tables_with_user_context(
        self,
        db: Session,
        question: str,
        selected_tables: list[str],
        user_id: int,
    ) -> dict:
        try:
            return self._route_tables(
                db,
                question,
                selected_tables,
                user_id=user_id,
            )
        except TypeError:
            # backward compatibility for tests/mocks monkeypatching old signature
            return self._route_tables(db, question, selected_tables)

    @staticmethod
    def _emit_progress(
        progress_callback: ProgressCallback | None,
        event: str,
        data: dict,
    ) -> None:
        """向 SSE 流式调用推送一个进度事件；非流式调用（callback 为空）时直接跳过。

        进度回调异常一律吞掉，避免「推进度」这种附属动作影响主查询流程。
        """
        if progress_callback is None:
            return
        try:
            progress_callback(event, data)
        except Exception:  # noqa: BLE001
            _console_logger.exception("progress callback failed: event=%s", event)

    def query(
        self,
        question: str,
        db: Session,
        runtime_config: dict | None = None,
        user_id: int | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        """执行完整问答流水线并返回结果载荷（含 SQL、列、数据行、自然语言回答）。

        这是「真正执行 SQL 并返回数据」的对外入口，全程包裹日志与异常兜底：
        - 成功：写「成功日志」并返回结果；
        - 路由信号不足（Text2SQLClarificationNeeded）：不报错，转为返回澄清提问；
        - 其它异常：写「失败日志」后向上抛出。
        progress_callback 不为空表示 SSE 流式调用，会逐阶段回推进度事件。
        """
        resolved_user_id = self._resolve_user_id(user_id)
        runtime = dict(runtime_config or {})
        selected_tables = self._normalize_table_list(runtime.get("selected_tables"))
        prompt_hint = str(runtime.get("prompt_hint") or "")
        conversation_context = self._build_conversation_context(runtime.get("history"))
        request_id = str(runtime.get("request_id") or uuid.uuid4().hex[:8])
        start = time.monotonic_ns()
        generated_sql: str | None = None
        final_sql: str | None = None
        repaired = False
        _console_logger.info(
            "[query:%s] start question=%s",
            request_id,
            self._truncate_text(question, 400),
        )
        try:
            payload = self._run_pipeline(
                db=db,
                question=question,
                selected_tables=selected_tables,
                prompt_hint=prompt_hint,
                execute_sql=True,
                user_id=resolved_user_id,
                progress_callback=progress_callback,
                conversation_context=conversation_context,
            )
            generated_sql = payload["generated_sql"]
            final_sql = payload["sql"]
            repaired = bool(payload.get("repaired"))
            effective_tables = self._normalize_table_list(payload.get("selected_tables") or selected_tables)
            payload["log_id"] = None

            # 记录成功日志：日志写失败不能影响已经成功的查询结果，故单独 try 并回滚。
            duration_ms = int((time.monotonic_ns() - start) / 1_000_000)
            if settings.TEXT2SQL_QUERY_LOG_ENABLED:
                try:
                    payload["log_id"] = self.log_service.create_success_log(
                        db=db,
                        user_id=resolved_user_id,
                        question=question,
                        generated_sql=generated_sql,
                        final_sql=final_sql,
                        runtime_config={
                            "selected_tables": effective_tables,
                            "prompt_hint": prompt_hint,
                            "relation_guard_used": bool(payload.get("relation_guard_used", False)),
                        },
                        row_count=len(payload["rows"]),
                        duration_ms=duration_ms,
                        repaired=repaired,
                    )
                except Exception as log_exc:  # noqa: BLE001
                    db.rollback()
                    _console_logger.warning(
                        "[query:%s] success-log write failed: %s",
                        request_id,
                        self._truncate_text(str(log_exc), 300),
                    )

            _console_logger.info(
                "[query:%s] success tables=%s duration_ms=%s row_count=%s sql=%s sample_rows=%s",
                request_id,
                json.dumps(effective_tables, ensure_ascii=False),
                duration_ms,
                len(payload.get("rows") or []),
                self._truncate_text(final_sql, 600),
                json.dumps(self._sample_rows_for_log(payload.get("rows") or []), ensure_ascii=False),
            )
            return payload
        except Text2SQLClarificationNeeded as exc:
            # 路由阶段判定信息不足，返回 mode=clarify 的澄清回复（前端据此提示用户补充条件），
            # 这是正常业务分支而非错误，因此不写失败日志、不向上抛异常。
            duration_ms = int((time.monotonic_ns() - start) / 1_000_000)
            _console_logger.info(
                "[query:%s] clarification duration_ms=%s question=%s",
                request_id,
                duration_ms,
                self._truncate_text(question, 400),
            )
            return {
                "mode": "clarify",
                "sql": "",
                "log_id": None,
                "columns": [],
                "rows": [],
                "answer": exc.clarify_question,
                "clarification": exc.clarify_question,
                "repaired": False,
                "field_inference": [],
                "selected_tables": [],
            }
        except Exception as exc:  # noqa: BLE001
            # 其它异常：记录失败日志后原样抛出，交由 router 转成统一错误响应。
            duration_ms = int((time.monotonic_ns() - start) / 1_000_000)
            if settings.TEXT2SQL_QUERY_LOG_ENABLED:
                try:
                    self.log_service.create_failed_log(
                        db=db,
                        user_id=resolved_user_id,
                        question=question,
                        generated_sql=generated_sql,
                        final_sql=final_sql,
                        runtime_config={
                            "selected_tables": selected_tables,
                            "prompt_hint": prompt_hint,
                            "relation_guard_used": False,
                        },
                        error_message=str(exc),
                        duration_ms=duration_ms,
                        repaired=repaired,
                    )
                except Exception as log_exc:  # noqa: BLE001
                    db.rollback()
                    _console_logger.warning(
                        "[query:%s] failed-log write failed: %s",
                        request_id,
                        self._truncate_text(str(log_exc), 300),
                    )
            _console_logger.exception(
                "[query:%s] failed duration_ms=%s error=%s",
                request_id,
                duration_ms,
                self._truncate_text(str(exc), 400),
            )
            raise

    def debug_generate(
        self,
        question: str,
        db: Session,
        runtime_config: dict | None = None,
        user_id: int | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        """仅执行「路由 + 生成 + 校验」，不真正执行 SQL（用于调试/预览生成的 SQL）。

        与 query() 共用同一条流水线，区别是 execute_sql=False，因此不连业务库、不出数据与摘要，
        只返回 SQL 文本、命中的候选表、路由打分、校验结论等调试信息。
        """
        resolved_user_id = self._resolve_user_id(user_id)
        runtime = dict(runtime_config or {})
        selected_tables = self._normalize_table_list(runtime.get("selected_tables"))
        prompt_hint = str(runtime.get("prompt_hint") or "")
        conversation_context = self._build_conversation_context(runtime.get("history"))
        request_id = str(runtime.get("request_id") or uuid.uuid4().hex[:8])
        _console_logger.info(
            "[debug:%s] start question=%s",
            request_id,
            self._truncate_text(question, 400),
        )
        try:
            result = self._run_pipeline(
                db=db,
                question=question,
                selected_tables=selected_tables,
                prompt_hint=prompt_hint,
                execute_sql=False,
                user_id=resolved_user_id,
                progress_callback=progress_callback,
                conversation_context=conversation_context,
            )
            _console_logger.info(
                "[debug:%s] done validation=%s sql=%s",
                request_id,
                bool(result.get("validation_passed")),
                self._truncate_text(str(result.get("sql") or ""), 600),
            )
            return result
        except Exception as exc:  # noqa: BLE001
            _console_logger.exception(
                "[debug:%s] failed error=%s",
                request_id,
                self._truncate_text(str(exc), 400),
            )
            raise

    def list_schema_overview(self, db: Session, table_names: list[str] | None = None):
        """返回指定表的结构概览（透传给 schema_service，供前端展示表/字段信息）。"""
        return self.schema_service.list_schema_overview(db, table_names)

    def _run_pipeline(
        self,
        *,
        db: Session,
        question: str,
        selected_tables: list[str],
        prompt_hint: str,
        execute_sql: bool,
        user_id: int | None = None,
        progress_callback: ProgressCallback | None = None,
        conversation_context: str = "",
    ) -> dict:
        """流水线核心：路由 → 关系守卫 → 生成/校验/修复 → （可选）执行 → 摘要。

        execute_sql 控制是否真正落到业务库执行：query() 传 True，debug_generate() 传 False。
        返回的 payload 在两种模式下字段不同（执行模式额外含 columns/rows/answer/field_inference）。
        """
        resolved_user_id = self._resolve_user_id(user_id)
        # 第 1 步：表路由——从用户可查询的表里挑出候选表集合及其关系提示。
        route = self._route_tables_with_user_context(
            db,
            question,
            selected_tables,
            resolved_user_id,
        )
        route_candidates = self._normalize_table_list(route.get("candidates") or [])
        route_pool_candidates = self._normalize_table_list(route.get("route_pool_tables") or route_candidates)
        route_relation_hints = list(route.get("relation_hints") or [])
        if not route_candidates:
            # 路由没命中任何可查询表：抛澄清异常，由 query() 转成澄清回复。
            raise Text2SQLClarificationNeeded(
                str(route.get("clarify_question") or "Current question does not match any queryable table")
            )

        max_join_tables = max(1, int(settings.TEXT2SQL_MAX_JOIN_TABLES or 1))
        multi_table_enabled = bool(settings.TEXT2SQL_MULTI_TABLE_ENABLED)
        # 多表关闭时只取第一张表；多表开启时最多取 max_join_tables 张。
        effective_candidates = route_candidates[: max_join_tables if multi_table_enabled else 1]

        # 第 2 步：关系守卫——确保多表查询时一定有 JOIN 关系兜底，否则降级回单表，
        # 杜绝模型在没有关系约束的情况下「凭空 JOIN」产生笛卡尔积或错误结果。
        relation_hints = route_relation_hints if len(effective_candidates) > 1 else []
        if multi_table_enabled:
            if len(effective_candidates) > 1 and not relation_hints:
                # 多表候选但路由未带关系提示：现查这些表之间「已启用」的关系。
                relation_hints = self._active_relations(
                    db,
                    effective_candidates,
                    resolved_user_id,
                )
                if not relation_hints and len(route_pool_candidates) > len(effective_candidates):
                    # 候选两两之间无关系：以第一张（得分最高）表为种子，从更大的候选池里
                    # 拉入与种子直接相连的邻居表，并按路由得分排序后重新组成候选集。
                    seed_table = effective_candidates[0]
                    pool_hints = self._active_relations(
                        db,
                        route_pool_candidates,
                        resolved_user_id,
                    )
                    related_tables = self._collect_related_tables(seed_table, pool_hints)
                    if related_tables:
                        route_scores = dict(route.get("scores") or {})
                        related_tables.sort(
                            key=lambda table_name: (-float(route_scores.get(table_name, 0.0)), table_name)
                        )
                        effective_candidates = [seed_table] + related_tables[: max_join_tables - 1]
                        relation_hints = self._active_relations(
                            db,
                            effective_candidates,
                            resolved_user_id,
                        )
            elif len(effective_candidates) == 1 and max_join_tables > 1:
                # 路由只给了一张表、但允许多表：尝试在用户选定范围内扩展与之有关系的邻居表，
                # 让「订单 + 订单明细」这类天然需要 JOIN 的问题也能补全关联表。
                seed_table = effective_candidates[0]
                expanded_scope = self._normalize_table_list(
                    self._queryable_table_names(
                        db,
                        selected_tables or None,
                        resolved_user_id,
                    )
                )
                if len(expanded_scope) > 1:
                    scoped_hints = self._active_relations(
                        db,
                        expanded_scope,
                        resolved_user_id,
                    )
                    related_tables = self._collect_related_tables(seed_table, scoped_hints)
                    if related_tables:
                        route_scores = dict(route.get("scores") or {})
                        related_tables.sort(
                            key=lambda table_name: (-float(route_scores.get(table_name, 0.0)), table_name)
                        )
                        effective_candidates = [seed_table] + related_tables[: max_join_tables - 1]
                        relation_hints = self._active_relations(
                            db,
                            effective_candidates,
                            resolved_user_id,
                        )
            if len(effective_candidates) > 1 and not relation_hints:
                # 兜底：多表但仍找不到任何关系，安全降级为单表，避免无约束 JOIN。
                effective_candidates = [effective_candidates[0]]
                relation_hints = []

        # relation_guard_used：本次是否真正进入「带关系约束的多表」模式（影响后续校验的最大表数）。
        relation_guard_used = bool(relation_hints) and len(effective_candidates) > 1
        self._emit_progress(
            progress_callback,
            "selected_tables",
            {
                "selected_tables": list(effective_candidates),
                "route_mode": str(route.get("mode") or "single"),
            },
        )
        # 第 3 步：装配生成所需上下文——可查询字段、枚举提示、few-shot 样例。
        candidate_columns_map = self._queryable_columns_map(
            db,
            effective_candidates,
            resolved_user_id,
        )
        # 枚举提示：把候选字段的可选枚举值喂给模型，减少「状态='已完成'」之类字面量写错。
        enhanced_prompt_hint = prompt_hint
        if settings.TEXT2SQL_ENUM_HINT_ENABLED:
            enhanced_prompt_hint = self.enum_hint_service.build_prompt_hint(
                db=db,
                candidate_tables=effective_candidates,
                queryable_columns_map=candidate_columns_map,
                base_prompt_hint=prompt_hint,
            )
        # few-shot：召回与当前问题相似的历史高分查询作为示范样例（失败不影响主流程）。
        few_shot_examples = "(no historical examples)"
        if self._is_few_shot_enabled():
            try:
                few_shot_examples = self.few_shot_service.search_similar_examples(
                    db,
                    question,
                    table_names=effective_candidates,
                )
            except Exception:  # noqa: BLE001
                _console_logger.exception("few-shot retrieval failed")
        repair_rounds = max(0, int(settings.TEXT2SQL_AUTO_REPAIR_ROUNDS))
        evaluate_kwargs: dict[str, Any] = {
            "db": db,
            "question": question,
            "candidate_tables": effective_candidates,
            "prompt_hint": enhanced_prompt_hint,
            "few_shot_examples": few_shot_examples,
            "candidate_columns_map": candidate_columns_map,
            "relation_hints": relation_hints,
            "repair_rounds": repair_rounds,
            "max_tables": max_join_tables if relation_guard_used else 1,
            "conversation_context": conversation_context,
        }
        # 第 4 步：生成 + 校验 + 修复。
        # 开启 self-consistency（N>1）且需要执行时，走多候选投票；否则单次确定性生成（温度 0）。
        # self-consistency 投票命中时复用胜出候选的执行结果，避免对同一条 SQL 二次执行。
        voted_columns: list[str] | None = None
        voted_rows: list[dict] | None = None
        self_consistency_n = max(1, int(settings.TEXT2SQL_SELF_CONSISTENCY_N or 1))
        if execute_sql and self_consistency_n > 1:
            voted_result = self._evaluate_with_voting(**evaluate_kwargs)
            if voted_result is not None:
                result, voted_columns, voted_rows = voted_result
            else:
                # 投票未产出任何可执行候选时，退回单次确定性生成。
                result = self._run_with_temperature(
                    0.0,
                    lambda: self._evaluate_candidates(**evaluate_kwargs),
                )
        else:
            result = self._run_with_temperature(
                0.0,
                lambda: self._evaluate_candidates(**evaluate_kwargs),
            )
        self._emit_progress(
            progress_callback,
            "generated_sql",
            {
                "sql": str(result.generated_sql or ""),
                "final_sql": str(result.final_sql or ""),
            },
        )
        if not result.is_valid:
            # 经过若干轮修复仍未通过校验：放弃执行，抛错由上层兜底。
            raise ValueError(f"SQL validation failed: {result.validation_message}")

        # 第 5 步：修正最终 mode 标签，便于前端/日志区分单表、多表、各种降级回退场景。
        effective_mode = str(route.get("mode") or "single")
        if relation_guard_used and len(effective_candidates) > 1 and effective_mode == "single":
            effective_mode = "multi_relation_fallback"
        elif relation_guard_used and len(effective_candidates) > 1:
            effective_mode = "multi"
        if not relation_guard_used and len(route_candidates) > 1 and len(effective_candidates) == 1:
            effective_mode = "single_fallback"

        payload = {
            "mode": effective_mode,
            "candidate_tables": effective_candidates,
            "route_pool_tables": route_pool_candidates,
            "route_scores": route["scores"],
            "selected_tables": effective_candidates,
            "generated_sql": result.generated_sql,
            "sql": result.final_sql,
            "validation_passed": result.is_valid,
            "validation_message": result.validation_message,
            "repair_attempts": result.repair_attempts,
            "repaired": result.repair_attempts > 0,
            "relation_guard_used": relation_guard_used,
            "relation_hints": self.relation_service.relation_hint_lines(relation_hints),
        }
        if execute_sql:
            # 第 6 步：执行 SQL 并出数据。投票已拿到结果则直接复用，否则现场执行。
            max_tables_for_validation = max_join_tables if relation_guard_used else 1
            table_columns_map = self.schema_service.get_live_table_columns_map(
                db,
                effective_candidates,
                queryable_columns_map=result.candidate_columns_map,
            )
            self._emit_progress(
                progress_callback,
                "status",
                {"step": "executing_sql", "message": "正在执行 SQL..."},
            )
            if voted_columns is not None and voted_rows is not None:
                columns, rows = voted_columns, voted_rows
            else:
                columns, rows = self.executor_service.execute_sql(db, result.final_sql)
            # 空结果二次探测：SQL 合法但查出 0 行，往往是过滤条件里的字面量（枚举值）写错了。
            # 此时拿该字段的真实枚举值再生成一次，纠正字面量后重试。
            empty_result_repaired = False
            if not rows and settings.TEXT2SQL_ENUM_HINT_ENABLED:
                empty_result_retry = self._retry_empty_result_with_enum_probe(
                    db=db,
                    question=question,
                    sql=result.final_sql,
                    prompt_hint=prompt_hint,
                    candidate_tables=effective_candidates,
                    candidate_columns_map=result.candidate_columns_map,
                    table_columns_map=table_columns_map,
                    relation_hints=relation_hints,
                    max_tables=max_tables_for_validation,
                )
                if empty_result_retry is not None:
                    payload["sql"] = empty_result_retry["sql"]
                    columns = list(empty_result_retry["columns"])
                    rows = list(empty_result_retry["rows"])
                    payload["repair_attempts"] = int(payload.get("repair_attempts") or 0) + 1
                    payload["repaired"] = True
                    empty_result_repaired = True

            if not empty_result_repaired:
                payload["repaired"] = bool(payload.get("repaired"))

            field_inference = self.field_permission_service.build_query_field_comment_bindings(
                db=db,
                columns=columns,
                table_names=effective_candidates,
                queryable_columns_map=result.candidate_columns_map,
            )
            resolved_sql = str(payload.get("sql") or result.final_sql)
            self._emit_progress(
                progress_callback,
                "sql_result",
                {
                    "sql": resolved_sql,
                    "columns": list(columns),
                    "rows": list(rows),
                    "row_count": len(rows),
                    "repaired": bool(payload.get("repaired")),
                    "field_inference": list(field_inference),
                },
            )

            # 第 7 步：生成自然语言回答。非流式直接返回整段；流式则逐块回推 answer_delta。
            self._emit_progress(
                progress_callback,
                "status",
                {"step": "summarizing", "message": "正在生成结果摘要..."},
            )
            if progress_callback is None:
                answer = self.summary_service.summarize_result(
                    question,
                    resolved_sql,
                    columns,
                    rows,
                )
            else:
                answer_chunks: list[str] = []
                for chunk in self.summary_service.stream_summarize_result(question, resolved_sql, columns, rows):
                    if not chunk:
                        continue
                    answer_chunks.append(chunk)
                    self._emit_progress(
                        progress_callback,
                        "answer_delta",
                        {"content": str(chunk)},
                    )
                answer = "".join(answer_chunks).strip()
                if not answer:
                    answer = self.summary_service.build_fallback_summary(columns, rows)

            payload.update(
                {
                    "columns": columns,
                    "rows": rows,
                    "answer": answer,
                    "field_inference": field_inference,
                }
            )
        return payload

    def _retry_empty_result_with_enum_probe(
        self,
        *,
        db: Session,
        question: str,
        sql: str,
        prompt_hint: str,
        candidate_tables: list[str],
        candidate_columns_map: dict[str, set[str]],
        table_columns_map: dict[str, set[str]],
        relation_hints: list[dict],
        max_tables: int,
    ) -> dict[str, object] | None:
        """空结果补救：针对过滤条件里的字面量字段，注入真实枚举值后重生成并重试一次。

        仅当能从 SQL 中提取出「字段 = 字面量 / IN (字面量...)」的目标字段、且为这些字段
        生成了与原 prompt 不同的枚举提示时才会尝试；重试 SQL 须再次通过校验。
        无可纠正项或重试无效时返回 None（保持原空结果）。
        """
        # 提取 SQL 中等值/IN 过滤所用的字段（最可能因枚举字面量写错而查空）。
        target_columns_map = self._extract_literal_filter_columns(sql, candidate_columns_map)
        if not target_columns_map:
            return None

        targeted_hint = self.enum_hint_service.build_prompt_hint(
            db=db,
            candidate_tables=list(target_columns_map.keys()),
            queryable_columns_map=target_columns_map,
            base_prompt_hint=prompt_hint,
        )
        if str(targeted_hint or "").strip() == str(prompt_hint or "").strip():
            return None

        repair_error_message = (
            "SQL validation passed but execution returned 0 rows. "
            "Use enum_hints_json to correct only literal values in '=' / IN filters for the same fields."
        )
        runtime_config = {
            "selected_tables": candidate_tables,
            "prompt_hint": targeted_hint,
            "queryable_columns_map": candidate_columns_map,
            "relation_hints": relation_hints,
        }
        repaired_sql = self.repair_service.repair_sql(
            db=db,
            question=question,
            failed_sql=sql,
            error_message=repair_error_message,
            runtime_config=runtime_config,
        )
        repaired_sql = self._strip_table_aliases(repaired_sql)
        repaired_sql = self._expand_select_star(repaired_sql, table_columns_map)
        repaired_sql = self._ensure_limit(repaired_sql)
        if repaired_sql.strip().rstrip(";") == str(sql or "").strip().rstrip(";"):
            return None

        is_valid, _ = self.validator_service.validate_sql(
            repaired_sql,
            allowed_tables=candidate_tables,
            table_columns_map=table_columns_map,
            max_tables=max_tables,
            relation_hints=relation_hints,
        )
        if not is_valid:
            return None

        columns, rows = self.executor_service.execute_sql(db, repaired_sql)
        return {
            "sql": repaired_sql,
            "columns": columns,
            "rows": rows,
        }

    @classmethod
    def _extract_literal_filter_columns(
        cls,
        sql: str,
        candidate_columns_map: dict[str, set[str]],
    ) -> dict[str, set[str]]:
        """解析 SQL，提取「等值 / IN 过滤」中用到的字段，返回 {表名: 字段集合}。

        只保留能在候选字段映射中唯一定位到归属表的字段；解析失败或定位不唯一时跳过该字段。
        """
        sql_text = str(sql or "").strip().rstrip(";")
        if not sql_text:
            return {}
        try:
            tree = parse_one(sql_text, read="mysql")
        except Exception:  # noqa: BLE001
            return {}

        normalized_columns_map = Text2SQLValidatorService.normalize_table_columns_map(candidate_columns_map)
        if not normalized_columns_map:
            return {}
        table_name_lookup = {
            Text2SQLValidatorService.normalize_table_identifier(table_name): str(table_name).strip()
            for table_name in (candidate_columns_map or {})
            if Text2SQLValidatorService.normalize_table_identifier(table_name)
        }

        alias_map = Text2SQLValidatorService.build_alias_map(tree)
        normalized_alias_map = {
            Text2SQLValidatorService.normalize_identifier(alias): Text2SQLValidatorService.normalize_table_identifier(table_name)
            for alias, table_name in alias_map.items()
            if Text2SQLValidatorService.normalize_identifier(alias) and Text2SQLValidatorService.normalize_table_identifier(table_name)
        }
        involved_tables = set(normalized_alias_map.values())

        targets: dict[str, set[str]] = {}

        def add_target(column_expr: exp.Expression | None) -> None:
            endpoint = cls._resolve_filter_column_endpoint(
                column_expr=column_expr,
                normalized_alias_map=normalized_alias_map,
                involved_tables=involved_tables,
                normalized_columns_map=normalized_columns_map,
            )
            if endpoint is None:
                return
            table_name, column_name = endpoint
            real_table_name = table_name_lookup.get(table_name, table_name)
            targets.setdefault(real_table_name, set()).add(column_name)

        for condition in tree.find_all(exp.EQ):
            if isinstance(condition.this, exp.Column) and isinstance(condition.expression, exp.Literal):
                add_target(condition.this)
            elif isinstance(condition.this, exp.Literal) and isinstance(condition.expression, exp.Column):
                add_target(condition.expression)

        for condition in tree.find_all(exp.In):
            if not isinstance(condition.this, exp.Column):
                continue
            expressions = list(condition.expressions or [])
            if not expressions:
                continue
            if not all(isinstance(item, exp.Literal) for item in expressions):
                continue
            add_target(condition.this)
        return targets

    @staticmethod
    def _resolve_filter_column_endpoint(
        *,
        column_expr: exp.Expression | None,
        normalized_alias_map: dict[str, str],
        involved_tables: set[str],
        normalized_columns_map: dict[str, set[str]],
    ) -> tuple[str, str] | None:
        if not isinstance(column_expr, exp.Column):
            return None
        normalized_column = Text2SQLValidatorService.normalize_identifier(str(column_expr.name or ""))
        if not normalized_column:
            return None

        table_alias = Text2SQLValidatorService.normalize_identifier(str(column_expr.table or ""))
        if table_alias:
            normalized_table = normalized_alias_map.get(table_alias)
            if not normalized_table:
                return None
            if normalized_column not in normalized_columns_map.get(normalized_table, set()):
                return None
            return normalized_table, normalized_column

        matched_tables = [
            table_name
            for table_name in involved_tables
            if normalized_column in normalized_columns_map.get(table_name, set())
        ]
        if len(matched_tables) != 1:
            return None
        return matched_tables[0], normalized_column

    def _evaluate_candidates(
        self,
        *,
        db: Session,
        question: str,
        candidate_tables: list[str],
        prompt_hint: str,
        few_shot_examples: str,
        candidate_columns_map: dict[str, set[str]],
        relation_hints: list[dict],
        repair_rounds: int,
        max_tables: int,
        conversation_context: str = "",
    ) -> SQLAttemptResult:
        """在候选表上生成一条 SQL，并在校验不通过时循环修复（最多 repair_rounds 轮）。

        生成后会统一做后处理：剥离表别名、把 SELECT * 展开为权限内的显式列、补默认 LIMIT，
        再交给校验器校验；每轮修复都重复「修复 → 后处理 → 再校验」直到通过或耗尽轮数。
        """
        table_columns_map = self.schema_service.get_live_table_columns_map(
            db,
            candidate_tables,
            queryable_columns_map=candidate_columns_map,
        )
        if not table_columns_map:
            raise ValueError("No queryable columns are enabled. Enable at least one column first.")
        runtime_config = {
            "selected_tables": candidate_tables,
            "prompt_hint": prompt_hint,
            "few_shot_examples": few_shot_examples,
            "queryable_columns_map": candidate_columns_map,
            "relation_hints": relation_hints,
            "conversation_context": conversation_context or "（无）",
        }
        generated_sql = self.generator_service.generate_sql(
            db=db,
            question=question,
            runtime_config=runtime_config,
        )
        generated_sql = self._strip_table_aliases(generated_sql)
        generated_sql = self._expand_select_star(generated_sql, table_columns_map)
        final_sql = self._ensure_limit(generated_sql)
        is_valid, message = self.validator_service.validate_sql(
            final_sql,
            allowed_tables=candidate_tables,
            table_columns_map=table_columns_map,
            max_tables=max_tables,
            relation_hints=relation_hints,
        )
        # 校验未过则进入自动修复循环：把校验失败原因回灌给模型，迭代修复直至通过或用尽轮数。
        repair_attempts = 0
        while not is_valid and repair_attempts < repair_rounds:
            repair_attempts += 1
            repaired_sql = self.repair_service.repair_sql(
                db=db,
                question=question,
                failed_sql=final_sql,
                error_message=message,
                runtime_config=runtime_config,
            )
            repaired_sql = self._strip_table_aliases(repaired_sql)
            repaired_sql = self._expand_select_star(repaired_sql, table_columns_map)
            final_sql = self._ensure_limit(repaired_sql)
            is_valid, message = self.validator_service.validate_sql(
                final_sql,
                allowed_tables=candidate_tables,
                table_columns_map=table_columns_map,
                max_tables=max_tables,
                relation_hints=relation_hints,
            )
        return SQLAttemptResult(
            generated_sql=generated_sql,
            final_sql=final_sql,
            is_valid=is_valid,
            validation_message=message,
            repair_attempts=repair_attempts,
            candidate_columns_map=candidate_columns_map,
        )

    def _run_with_temperature(self, temperature: float, operation: Callable[[], Any]) -> Any:
        """在指定采样温度下执行 operation，结束后恢复原温度（用于多候选采样）。"""
        previous_temperature = float(self._current_temperature)
        self._current_temperature = max(0.0, float(temperature))
        try:
            return operation()
        finally:
            self._current_temperature = previous_temperature

    @staticmethod
    def _result_signature(columns: list[str], rows: list[dict]) -> str:
        """将查询结果归一化为可比较的签名字符串，用于 self-consistency 投票分桶。"""
        normalized_columns = [str(item) for item in (columns or [])]
        normalized_rows: list[str] = []
        for row in rows or []:
            if isinstance(row, dict):
                normalized_row = {
                    str(key): (value if value is None or isinstance(value, (int, float, bool)) else str(value))
                    for key, value in sorted(row.items(), key=lambda item: str(item[0]))
                }
            else:
                normalized_row = {"_value": str(row)}
            normalized_rows.append(json.dumps(normalized_row, ensure_ascii=False, sort_keys=True))
        normalized_rows.sort()
        payload = {
            "columns": normalized_columns,
            "rows": normalized_rows,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _evaluate_with_voting(
        self,
        *,
        db: Session,
        question: str,
        candidate_tables: list[str],
        prompt_hint: str,
        few_shot_examples: str,
        candidate_columns_map: dict[str, set[str]],
        relation_hints: list[dict],
        repair_rounds: int,
        max_tables: int,
        conversation_context: str = "",
    ) -> tuple[SQLAttemptResult, list[str], list[dict]] | None:
        """self-consistency：生成多个候选 SQL 并执行，按结果签名投票，多数胜出。

        第 1 个候选用温度 0（确定性），其余使用采样温度以产生多样性。
        平局时优先选修复次数更少、序号更靠前的候选。无任何可执行候选时返回 None。
        """
        candidate_count = max(1, int(settings.TEXT2SQL_SELF_CONSISTENCY_N or 1))
        sampling_temperature = max(0.0, float(settings.TEXT2SQL_SELF_CONSISTENCY_TEMPERATURE or 0.0))
        executed_candidates: list[dict[str, Any]] = []
        for index in range(candidate_count):
            temperature = 0.0 if index == 0 else sampling_temperature
            try:
                attempt = self._run_with_temperature(
                    temperature,
                    lambda: self._evaluate_candidates(
                        db=db,
                        question=question,
                        candidate_tables=candidate_tables,
                        prompt_hint=prompt_hint,
                        few_shot_examples=few_shot_examples,
                        candidate_columns_map=candidate_columns_map,
                        relation_hints=relation_hints,
                        repair_rounds=repair_rounds,
                        max_tables=max_tables,
                        conversation_context=conversation_context,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                _console_logger.warning(
                    "[self-consistency] candidate=%s evaluate failed: %s",
                    index,
                    self._truncate_text(str(exc), 240),
                )
                continue
            if not attempt.is_valid:
                continue
            try:
                columns, rows = self.executor_service.execute_sql(db, attempt.final_sql)
            except Exception as exc:  # noqa: BLE001
                _console_logger.warning(
                    "[self-consistency] candidate=%s execute failed: %s",
                    index,
                    self._truncate_text(str(exc), 240),
                )
                continue
            executed_candidates.append(
                {
                    "index": index,
                    "attempt": attempt,
                    "columns": columns,
                    "rows": rows,
                    "signature": self._result_signature(columns, rows),
                }
            )
        if not executed_candidates:
            return None
        grouped: dict[str, list[dict[str, Any]]] = {}
        for candidate in executed_candidates:
            grouped.setdefault(str(candidate.get("signature") or ""), []).append(candidate)
        ranked_buckets = sorted(
            grouped.values(),
            key=lambda bucket: (
                -len(bucket),
                min(int(item["attempt"].repair_attempts) for item in bucket),
                min(int(item["index"]) for item in bucket),
            ),
        )
        winner_bucket = ranked_buckets[0]
        winner_bucket.sort(key=lambda item: (int(item["attempt"].repair_attempts), int(item["index"])))
        winner = winner_bucket[0]
        return winner["attempt"], winner["columns"], winner["rows"]

    @classmethod
    def _build_conversation_context(cls, history: Any, *, max_turns: int = 5) -> str:
        """把前端回传的多轮历史拼成提示词片段；无历史返回空串。"""
        if not isinstance(history, (list, tuple)) or not history:
            return ""
        turns: list[str] = []
        for raw_turn in list(history)[-max_turns:]:
            if isinstance(raw_turn, dict):
                turn_question = str(raw_turn.get("question") or "").strip()
                turn_sql = str(raw_turn.get("sql") or "").strip()
                turn_answer = str(raw_turn.get("answer") or "").strip()
            else:
                turn_question = str(getattr(raw_turn, "question", "") or "").strip()
                turn_sql = str(getattr(raw_turn, "sql", "") or "").strip()
                turn_answer = str(getattr(raw_turn, "answer", "") or "").strip()
            if not turn_question and not turn_sql and not turn_answer:
                continue
            lines = [f"用户问：{cls._truncate_text(turn_question, 300)}"]
            if turn_sql:
                lines.append(f"对应SQL：{cls._truncate_text(turn_sql, 400)}")
            if turn_answer:
                lines.append(f"回答：{cls._truncate_text(turn_answer, 300)}")
            turns.append("\n".join(lines))
        if not turns:
            return ""
        return "\n\n".join(f"[第{index + 1}轮]\n{block}" for index, block in enumerate(turns))

    @staticmethod
    def _contains_chinese(value: str) -> bool:
        return contains_chinese(value)

    @classmethod
    def _build_search_tokens(cls, text: str, *, max_tokens: int = 256) -> set[str]:
        return build_search_tokens(text, max_tokens=max_tokens)

    @classmethod
    def _build_table_profiles(
        cls,
        table_options: list[dict[str, str]],
        table_columns_map: dict[str, set[str]] | None = None,
    ) -> dict[str, str]:
        """构建表画像文本（表名 + 表注释 + 部分列名），作为关键词/画像打分的语料。"""

        # Keep only a limited number of columns to reduce noisy matches from huge tables.
        # Column names here are supplementary signals beyond table name/comment semantics.


        profiles: dict[str, str] = {}
        for option in table_options:
            table_name = str(option.get("table_name") or "").strip()
            if not table_name:
                continue
            table_comment = str(option.get("table_comment") or "").strip()
            columns = sorted(
                [
                    str(column).strip()
                    for column in (table_columns_map or {}).get(table_name, set())
                    if str(column).strip()
                ]
            )
            # Keep first 20 columns to avoid profile token noise.
            if len(columns) > 20:
                columns = columns[:20]
            columns_text = " ".join(columns)
            profile_text = f"{table_name} {table_comment} {columns_text}".strip()
            profiles[table_name] = profile_text
        return profiles

    @classmethod
    def _score_table_profile_candidates(cls, question: str, table_profiles: dict[str, str]) -> dict[str, float]:
        """画像打分：按「问题分词」与「表画像分词」的重叠数计分，并受上限（score_cap）约束。"""
        question_tokens = cls._build_search_tokens(question, max_tokens=320)
        scores: dict[str, float] = {}
        token_match_score = float(settings.TABLE_ROUTE_PROFILE_TOKEN_MATCH_SCORE or 0.0)
        score_cap = max(0.0, float(settings.TABLE_ROUTE_PROFILE_SCORE_CAP or 0.0))
        for table_name, profile in table_profiles.items():
            profile_tokens = cls._build_search_tokens(profile, max_tokens=320)
            if not profile_tokens:
                scores[table_name] = 0.0
                continue

            overlap = len(profile_tokens.intersection(question_tokens))
            score = round(min(score_cap, float(overlap) * token_match_score), 6)
            scores[table_name] = score
        return scores

    @staticmethod
    def _expand_pool_by_relation_graph(seed_tables: list[str], relation_hints: list[dict] | None) -> list[str]:
        """以种子表为中心，沿关系图扩展一跳邻居表，扩大多表候选池。"""
        expanded = [str(name).strip() for name in (seed_tables or []) if str(name).strip()]
        seen = {table_name.lower() for table_name in expanded}
        for seed_table in list(expanded):
            for related_table in Text2SQLFacadeService._collect_related_tables(seed_table, relation_hints):
                key = related_table.lower()
                if key in seen:
                    continue
                seen.add(key)
                expanded.append(related_table)
        return expanded

    @staticmethod
    def _build_router_output_fallback(candidates: list[str], max_tables: int) -> list[str]:
        """路由兜底：模型不可用/输出无效时，直接取候选前 max_tables 张表。"""
        if not candidates:
            return []
        safe_max_tables = max(1, int(max_tables or 1))
        return candidates[:safe_max_tables]

    @staticmethod
    def _normalize_router_selected_tables(raw_output: str, candidates: list[str]) -> list[str]:
        """解析大模型的路由输出并对齐到真实候选表名。

        容错处理多种格式：去除 ```代码块``` 包裹 → 尝试 JSON（{"tables":[...]} 或纯数组）
        → 退化为方括号/逗号切分；最后只保留能在候选集中（忽略大小写、归一化后）命中的表名。
        """
        cleaned = str(raw_output or "").strip()
        if not cleaned:
            return []
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```\w*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
            cleaned = cleaned.strip()

        parsed_tables: list[str] = []
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                raw_tables = parsed.get("tables")
                if isinstance(raw_tables, list):
                    parsed_tables = [str(item).strip() for item in raw_tables if str(item).strip()]
            elif isinstance(parsed, list):
                parsed_tables = [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:  # noqa: BLE001
            bracket_match = re.search(r"\[(.*?)\]", cleaned, flags=re.DOTALL)
            if bracket_match:
                raw_items = [item.strip() for item in bracket_match.group(1).split(",")]
                parsed_tables = [item.strip("`\"' ") for item in raw_items if item.strip()]
            else:
                raw_items = [item.strip() for item in cleaned.split(",")]
                parsed_tables = [item.strip("`\"' ") for item in raw_items if item.strip()]

        if not parsed_tables:
            return []

        lookup = {str(name).strip().lower(): str(name).strip() for name in (candidates or []) if str(name).strip()}
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_name in parsed_tables:
            candidate = lookup.get(str(raw_name).strip().lower())
            if not candidate:
                normalized_raw = Text2SQLValidatorService.normalize_table_identifier(raw_name)
                candidate = lookup.get(normalized_raw)
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(candidate)
        return normalized

    def _llm_route_tables(
        self,
        question: str,
        candidates: list[str],
        *,
        table_comment_map: dict[str, str],
        table_columns_map: dict[str, set[str]] | None = None,
        relation_hints: list[dict] | None = None,
        max_tables: int = 1,
    ) -> list[str]:
        """多表路由：让大模型在候选表 + JOIN 白名单约束下选出最小表集合（输出 JSON）。

        候选数≤1 或最多只允许 1 张表时直接走兜底；模型不可用或解析失败也回退兜底
        （取候选前 max_tables 张）。
        """
        if not candidates:
            return []

        safe_max_tables = max(1, int(max_tables or 1))
        fallback_tables = self._build_router_output_fallback(candidates, safe_max_tables)
        if len(candidates) <= 1 or safe_max_tables <= 1:
            return fallback_tables

        model = self._get_model()
        if model is None:
            return fallback_tables

        info_lines: list[str] = []
        for table_name in candidates:
            comment = table_comment_map.get(table_name, "").strip()
            label = f"{table_name} ({comment})" if comment else table_name
            columns = sorted(
                str(c).strip()
                for c in (table_columns_map or {}).get(table_name, set())
                if str(c).strip()
            )
            if len(columns) > 20:
                columns = columns[:20] + [f"... total {len(columns)} columns"]
            columns_text = ", ".join(columns) if columns else "(no queryable columns)"
            info_lines.append(f"- {label}\n  columns: {columns_text}")

        relation_hint_lines = self.relation_service.relation_hint_lines(relation_hints or [])
        relation_hints_text = "\n".join(relation_hint_lines) if relation_hint_lines else "(none)"
        chain = _ROUTER_TABLE_SELECTION_PROMPT | model | StrOutputParser()
        try:
            raw_output = str(
                chain.invoke(
                    {
                        "question": question,
                        "candidates_info": "\n".join(info_lines),
                        "relation_hints_text": relation_hints_text,
                    }
                )
            ).strip()
        except Exception:  # noqa: BLE001
            _console_logger.exception("router table selection LLM invoke failed")
            return fallback_tables

        selected_tables = self._normalize_router_selected_tables(raw_output, candidates)
        if not selected_tables:
            return fallback_tables
        return selected_tables[:safe_max_tables]

    def _route_tables(
        self,
        db: Session,
        question: str,
        selected_tables: list[str],
        user_id: int | None = None,
    ) -> dict:
        """表路由核心：从用户可查询的表里挑出回答问题所需的候选表集合。

        整体分为「召回 → 打分排序 → 关系图扩展 → 大模型决策」四步：
        1. 确定路由范围：用户显式选了表则以其为准，否则取连接下全部表，再按表/字段权限过滤。
        2. 召回 + 打分：向量召回（启用知识库时）粗筛 Top-K，再用「语义×关键词×画像」三路加权打分。
        3. 关系图扩展：以高分种子表为中心，沿关系白名单扩展一跳邻居，形成候选池。
        4. 大模型决策：多表模式让模型在候选池+JOIN 白名单内挑最小表集；单表模式只挑一张主表。

        返回 dict 含 mode（single/multi/miss/no_signal）、candidates、route_pool_tables、
        scores、relation_hints、clarify_question（信号不足时的澄清话术）。
        """
        resolved_user_id = self._resolve_user_id(user_id)
        # 第 1 步：确定路由范围——优先用户显式选定的表，否则取连接下全部表。
        if selected_tables:
            route_scope, _ = self.schema_service.validate_selected_tables(db, selected_tables)
        else:
            route_scope = self.schema_service.list_table_names(db)
        if not route_scope:
            return {
                "mode": "miss",
                "candidates": [],
                "scores": {},
                "clarify_question": "No routable tables are configured for current connection.",
            }

        queryable_tables = self._queryable_table_names(
            db,
            route_scope,
            resolved_user_id,
        )
        if not queryable_tables:
            return {
                "mode": "miss",
                "candidates": [],
                "scores": {},
                "clarify_question": "No queryable tables are available under current table/field permissions.",
            }

        # 第 2 步：召回。已选表/未启向量时直接全量进入打分；否则先用向量+关键词种子分粗筛 Top-K。
        vector_route_enabled = self._is_vector_route_enabled()
        kb_search_top_k = max(1, int(settings.TABLE_ROUTE_KB_SEARCH_TOP_K or 1))
        kb_recall_limit = max(1, int(settings.TABLE_ROUTE_KB_RECALL_CANDIDATES or kb_search_top_k))
        seed_vector_scores: dict[str, float] = {}
        recall_tables: list[str]
        if selected_tables:
            recall_tables = list(queryable_tables)
        elif not vector_route_enabled:
            recall_tables = list(queryable_tables)
        else:
            seed_vector_scores = self.vector_service.search_tables(
                db,
                question,
                candidate_tables=queryable_tables,
                top_k=kb_search_top_k,
                route_kb_id=int(settings.TABLE_ROUTE_KB_ID or 0),
            )
            seed_keyword_scores = self._score_table_name_candidates(question, queryable_tables)
            recall_ranked = sorted(
                queryable_tables,
                key=lambda table_name: (
                    -float(seed_vector_scores.get(table_name, 0.0)),
                    -float(seed_keyword_scores.get(table_name, 0.0)),
                    table_name,
                ),
            )
            has_seed_signal = any(
                float(seed_vector_scores.get(table_name, 0.0)) > 0.0
                or float(seed_keyword_scores.get(table_name, 0.0)) > 0.0
                for table_name in recall_ranked
            )
            if not has_seed_signal:
                return {
                    "mode": "no_signal",
                    "candidates": [],
                    "scores": {},
                    "clarify_question": "Knowledge base recall signal is weak. Please provide more specific business entities or filters.",
                }
            recall_count = min(kb_recall_limit, len(recall_ranked))
            recall_tables = recall_ranked[:recall_count]
            _console_logger.info(
                "[route] kb_recall tables=%s",
                json.dumps(recall_tables, ensure_ascii=False),
            )

        table_options = self.schema_service.list_table_options_by_names(db, recall_tables)
        option_comment_map = {
            str(option.get("table_name") or "").strip(): str(option.get("table_comment") or "").strip()
            for option in table_options
            if str(option.get("table_name") or "").strip()
        }
        scoring_tables = [table_name for table_name in recall_tables if table_name in option_comment_map]
        if not scoring_tables:
            return {
                "mode": "miss",
                "candidates": [],
                "scores": {},
                "clarify_question": "No evaluable tables are available under current routing constraints.",
            }

        queryable_columns_map = self._queryable_columns_map(
            db,
            scoring_tables,
            resolved_user_id,
        )
        scoring_tables = [table_name for table_name in scoring_tables if table_name in queryable_columns_map]
        if not scoring_tables:
            return {
                "mode": "miss",
                "candidates": [],
                "scores": {},
                "clarify_question": "No queryable tables are available under current table/field permissions.",
            }

        queryable_profiles = self._build_table_profiles(
            [
                {
                    "table_name": table_name,
                    "table_comment": option_comment_map.get(table_name, ""),
                }
                for table_name in scoring_tables
            ],
            table_columns_map=queryable_columns_map,
        )
        rerank_vector_scores = self.vector_service.search_tables(
            db,
            question,
            candidate_tables=scoring_tables,
            top_k=max(kb_search_top_k, len(scoring_tables)),
            candidate_profiles={name: queryable_profiles.get(name, "") for name in scoring_tables},
            route_kb_id=int(settings.TABLE_ROUTE_KB_ID or 0),
        )
        vector_scores = dict(seed_vector_scores)
        vector_scores.update(rerank_vector_scores)
        keyword_scores = self._score_table_name_candidates(question, scoring_tables)
        profile_scores = self._score_table_profile_candidates(question, queryable_profiles)

        # 三路加权打分：语义相似度（向量）×权重 + 表名关键词命中×权重 + 表画像命中×权重。
        # 三者权重均由配置控制，便于按场景调参；总分>0 的表才进入候选排序。
        final_scores: dict[str, float] = {}
        semantic_weight = float(settings.TABLE_ROUTE_SEMANTIC_SCORE_WEIGHT or 0.0)
        keyword_weight = float(settings.TABLE_ROUTE_KEYWORD_SCORE_WEIGHT or 0.0)
        profile_weight = float(settings.TABLE_ROUTE_PROFILE_SCORE_WEIGHT or 0.0)
        for table_name in scoring_tables:
            semantic_score = float(vector_scores.get(table_name, 0.0))
            keyword_score = float(keyword_scores.get(table_name, 0.0))
            profile_score = float(profile_scores.get(table_name, 0.0))
            total_score = round(
                semantic_score * semantic_weight
                + keyword_score * keyword_weight
                + profile_score * profile_weight,
                6,
            )
            if total_score > 0:
                final_scores[table_name] = total_score

        if not final_scores:
            if not vector_route_enabled:
                fallback_ranked = sorted(
                    scoring_tables,
                    key=lambda table_name: (
                        -float(keyword_scores.get(table_name, 0.0)),
                        -float(profile_scores.get(table_name, 0.0)),
                        table_name,
                    ),
                )
                final_scores = {
                    table_name: round(
                        float(keyword_scores.get(table_name, 0.0))
                        + float(profile_scores.get(table_name, 0.0)),
                        6,
                    )
                    for table_name in fallback_ranked
                }
            else:
                return {
                    "mode": "no_signal",
                    "candidates": [],
                    "scores": {},
                    "clarify_question": "Routing signal is weak. Please provide more specific business entities or filters.",
                }
        if not final_scores:
            return {
                "mode": "no_signal",
                "candidates": [],
                "scores": {},
                "clarify_question": "Routing signal is weak. Please provide more specific business entities or filters.",
            }

        # 第 3 步：取 Top-K 高分表作为种子，沿关系图扩展一跳邻居，构成最终候选池 route_pool_tables。
        ranked = sorted(final_scores.keys(), key=lambda t: (-final_scores.get(t, 0.0), t))
        config_top_k = max(1, int(settings.TABLE_ROUTE_MAX_CANDIDATES or 1))
        max_join_tables = max(1, int(settings.TEXT2SQL_MAX_JOIN_TABLES or 1))
        if bool(settings.TEXT2SQL_MULTI_TABLE_ENABLED):
            config_top_k = max(config_top_k, max_join_tables)
        top_k = min(config_top_k, len(ranked))
        seed_tables = ranked[:top_k]

        relation_scope_hints: list[dict] = []
        if bool(settings.TEXT2SQL_MULTI_TABLE_ENABLED) and len(queryable_tables) > 1:
            relation_scope_hints = self._active_relations(
                db,
                queryable_tables,
                resolved_user_id,
            )
        expanded_pool = self._expand_pool_by_relation_graph(seed_tables, relation_scope_hints)
        route_pool_tables = [table_name for table_name in expanded_pool if table_name in queryable_tables]
        if not route_pool_tables:
            route_pool_tables = list(seed_tables)

        route_pool_options = self.schema_service.list_table_options_by_names(db, route_pool_tables)
        route_pool_comment_map = {
            str(option.get("table_name") or "").strip(): str(option.get("table_comment") or "").strip()
            for option in route_pool_options
            if str(option.get("table_name") or "").strip()
        }
        route_pool_tables = [table_name for table_name in route_pool_tables if table_name in route_pool_comment_map]
        route_pool_columns_map = self._queryable_columns_map(
            db,
            route_pool_tables,
            resolved_user_id,
        )
        route_pool_tables = [table_name for table_name in route_pool_tables if table_name in route_pool_columns_map]
        if not route_pool_tables:
            return {
                "mode": "miss",
                "candidates": [],
                "scores": {},
                "clarify_question": "No queryable tables are available under current table/field permissions.",
            }

        route_pool_scores = {name: float(final_scores.get(name, 0.0)) for name in route_pool_tables}
        route_pool_tables = sorted(route_pool_tables, key=lambda name: (-route_pool_scores.get(name, 0.0), name))

        relation_hints_for_router = self._active_relations(
            db,
            route_pool_tables,
            resolved_user_id,
        )

        # 第 4 步：大模型决策。多表模式让模型在候选池+JOIN 白名单内挑最小表集；单表模式只挑一张主表。
        if bool(settings.TEXT2SQL_MULTI_TABLE_ENABLED):
            selected_candidate_tables = self._llm_route_tables(
                question,
                route_pool_tables,
                table_comment_map=route_pool_comment_map,
                table_columns_map=route_pool_columns_map,
                relation_hints=relation_hints_for_router,
                max_tables=max_join_tables,
            )
            mode = "multi" if len(selected_candidate_tables) > 1 else "single"
        else:
            best_table = self._llm_select_best_table(
                question,
                route_pool_tables,
                table_comment_map=route_pool_comment_map,
                table_columns_map=route_pool_columns_map,
            )
            selected_candidate_tables = [best_table] if best_table else []
            mode = "single"

        selected_candidate_tables = [
            table_name
            for table_name in self._normalize_table_list(selected_candidate_tables)
            if table_name in route_pool_tables
        ]
        if not selected_candidate_tables and route_pool_tables:
            selected_candidate_tables = [route_pool_tables[0]]

        relation_hints_for_selected: list[dict] = []
        if len(selected_candidate_tables) > 1:
            relation_hints_for_selected = self._active_relations(
                db,
                selected_candidate_tables,
                resolved_user_id,
            )
            if not relation_hints_for_selected:
                selected_candidate_tables = [selected_candidate_tables[0]]
                mode = "single"

        _console_logger.info(
            "[route] seed=%s expanded=%s selected=%s",
            json.dumps(seed_tables, ensure_ascii=False),
            json.dumps(route_pool_tables, ensure_ascii=False),
            json.dumps(selected_candidate_tables, ensure_ascii=False),
        )

        return {
            "mode": mode,
            "candidates": selected_candidate_tables,
            "route_pool_tables": route_pool_tables,
            "scores": route_pool_scores,
            "relation_hints": relation_hints_for_selected,
            "clarify_question": "",
        }

    def _llm_select_best_table(
        self,
        question: str,
        candidates: list[str],
        *,
        table_comment_map: dict[str, str],
        table_columns_map: dict[str, set[str]] | None = None,
    ) -> str:
        """让大模型从 Top-K 候选表中挑出最匹配的一张主表（单表路由模式）。

        模型输出做容错解析：精确命中候选名 → 名称包含匹配 → 兜底取第一名；调用失败也回退第一名。
        """
        if not candidates:
            return ""
        if len(candidates) <= 1:
            return candidates[0]

        model = self._get_model()
        if model is None:
            return candidates[0]

        # Build a compact candidate summary so the model can compare tables clearly.
        info_lines: list[str] = []
        for table_name in candidates:
            comment = table_comment_map.get(table_name, "").strip()
            label = f"{table_name} ({comment})" if comment else table_name
            columns = sorted(
                str(c).strip()
                for c in (table_columns_map or {}).get(table_name, set())
                if str(c).strip()
            )
            # Show at most 15 columns to keep prompt concise.
            if len(columns) > 15:
                columns = columns[:15] + [f"... total {len(columns)} columns"]
            columns_text = ", ".join(columns) if columns else "(no queryable columns)"
            info_lines.append(f"- {label}\n  columns: {columns_text}")

        candidates_info = "\n".join(info_lines)
        chain = _TABLE_SELECTION_PROMPT | model | StrOutputParser()
        try:
            selected = str(
                chain.invoke(
                    {
                        "question": question,
                        "candidates_info": candidates_info,
                    }
                )
            ).strip().strip("`").strip('"')
        except Exception:  # noqa: BLE001
            _console_logger.exception("table selection LLM invoke failed")
            return candidates[0]

        normalized_lookup = {
            str(name).strip().lower(): name for name in candidates if str(name).strip()
        }
        normalized_selected = str(selected).strip().lower()
        if normalized_selected in normalized_lookup:
            return normalized_lookup[normalized_selected]

        for key, table_name in normalized_lookup.items():
            if key and key in normalized_selected:
                return table_name
        return candidates[0]

    @classmethod
    def _score_table_name_candidates(cls, question: str, table_names: list[str]) -> dict[str, float]:
        """关键词打分：表名整体出现在问题中给「精确分」，表名分词命中问题分词再累加「分词分」。"""
        question_text = str(question or "").lower()
        question_tokens = cls._build_search_tokens(question_text, max_tokens=320)
        scores: dict[str, float] = {}
        exact_match_score = float(settings.TABLE_ROUTE_NAME_EXACT_MATCH_SCORE or 0.0)
        token_match_score = float(settings.TABLE_ROUTE_NAME_TOKEN_MATCH_SCORE or 0.0)
        for table_name in table_names:
            normalized_table = str(table_name or "").strip().lower()
            if not normalized_table:
                continue

            score = 0.0
            if normalized_table in question_text:
                score += exact_match_score

            for token in cls._build_search_tokens(normalized_table, max_tokens=64):
                if token in question_tokens:
                    score += token_match_score
            scores[table_name] = round(score, 6)
        return scores

    @staticmethod
    def _normalize_table_list(tables) -> list[str]:
        """把入参（字符串/列表/集合等）归一化为去重、去空、保序的表名列表。"""
        if not tables:
            return []
        if isinstance(tables, str):
            raw_tables = [tables]
        elif isinstance(tables, (list, tuple, set)):
            raw_tables = list(tables)
        else:
            raw_tables = [tables]
        result: list[str] = []
        seen = set()
        for item in raw_tables:
            table = str(item).strip()
            if not table:
                continue
            key = table.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(table)
        return result

    @staticmethod
    def _collect_related_tables(seed_table: str, relation_hints: list[dict] | None) -> list[str]:
        """从关系提示中找出与种子表「直接相连」的对端表（去重、忽略自环）。"""
        seed_key = str(seed_table or "").strip().lower()
        if not seed_key:
            return []
        related_tables: list[str] = []
        seen_related: set[str] = set()
        for hint in relation_hints or []:
            source_table = str(hint.get("source_table") or "").strip()
            target_table = str(hint.get("target_table") or "").strip()
            if not source_table or not target_table:
                continue
            source_key = source_table.lower()
            target_key = target_table.lower()
            related_table = ""
            if source_key == seed_key and target_key != seed_key:
                related_table = target_table
            elif target_key == seed_key and source_key != seed_key:
                related_table = source_table
            if not related_table:
                continue
            related_key = related_table.lower()
            if related_key in seen_related:
                continue
            seen_related.add(related_key)
            related_tables.append(related_table)
        return related_tables

    @staticmethod
    def _strip_table_aliases(sql: str) -> str:
        """剥离表别名，并把列限定符改写为完整表名。

        生成的 SQL 统一不使用别名，可让后续的字段权限校验、SELECT * 展开、字段注释绑定
        都能直接按「真实表名.列名」匹配，避免别名带来的歧义。
        """
        sql_text = str(sql or "").strip().rstrip(";")
        if not sql_text:
            return "SELECT 1;"
        try:
            tree = parse_one(sql_text, read="mysql")
        except Exception:  # noqa: BLE001
            return sql_text + ";"

        alias_to_table: dict[str, str] = {}
        for table in tree.find_all(exp.Table):
            table_name = str(table.name or "").strip()
            alias_name = str(table.alias or "").strip()
            if alias_name and table_name:
                alias_key = Text2SQLValidatorService.normalize_identifier(alias_name)
                if alias_key:
                    alias_to_table[alias_key] = table_name
                table.set("alias", None)

        if alias_to_table:
            for column in tree.find_all(exp.Column):
                table_qualifier = str(column.table or "").strip()
                if not table_qualifier:
                    continue
                qualifier_key = Text2SQLValidatorService.normalize_identifier(table_qualifier)
                real_table = alias_to_table.get(qualifier_key)
                if not real_table:
                    continue
                column.set("table", exp.to_identifier(real_table))

        normalized_sql = tree.sql(dialect="mysql").strip().rstrip(";")
        return normalized_sql + ";"

    @staticmethod
    def _expand_select_star(sql: str, table_columns_map: dict[str, set[str]]) -> str:
        """把 SELECT * / 表.* 展开为「权限范围内」的显式列。

        既避免把用户无权查看的字段带出去（越权），也让返回的结果列稳定可预期。
        """
        sql_text = str(sql or "").strip().rstrip(";")
        if not sql_text:
            return "SELECT 1;"
        try:
            tree = parse_one(sql_text, read="mysql")
        except Exception:  # noqa: BLE001
            return sql_text + ";"
        if not isinstance(tree, exp.Select):
            return sql_text + ";"
        normalized_table_columns_map: dict[str, list[str]] = {}
        for table_name, columns in (table_columns_map or {}).items():
            normalized_table = Text2SQLValidatorService.normalize_table_identifier(table_name)
            if not normalized_table:
                continue
            normalized_table_columns_map[normalized_table] = sorted(
                [str(column) for column in (columns or set()) if str(column).strip()]
            )
        alias_map = Text2SQLValidatorService.build_alias_map(tree)
        normalized_alias_map = {
            Text2SQLValidatorService.normalize_identifier(alias): str(real_table)
            for alias, real_table in alias_map.items()
            if alias and real_table
        }
        table_order: list[tuple[str, str]] = []
        seen_tables: set[str] = set()
        for table in tree.find_all(exp.Table):
            if not table.name:
                continue
            normalized_table = Text2SQLValidatorService.normalize_table_identifier(str(table.name))
            if not normalized_table or normalized_table in seen_tables:
                continue
            seen_tables.add(normalized_table)
            qualifier = str(table.alias_or_name or table.name)
            table_order.append((normalized_table, qualifier))
        replaced = False
        expanded_expressions: list[exp.Expression] = []
        for expression in list(tree.expressions):
            if isinstance(expression, exp.Star):
                replaced = True
                for table_name, qualifier in table_order:
                    for column_name in normalized_table_columns_map.get(table_name, []):
                        if len(table_order) > 1:
                            expanded_expressions.append(exp.column(column_name, table=qualifier))
                        else:
                            expanded_expressions.append(exp.column(column_name))
                continue

            if isinstance(expression, exp.Column) and isinstance(expression.this, exp.Star):
                table_alias = str(expression.table or "")
                alias_key = Text2SQLValidatorService.normalize_identifier(table_alias)
                resolved_table = normalized_alias_map.get(alias_key, table_alias)
                normalized_table = Text2SQLValidatorService.normalize_table_identifier(resolved_table)
                selected_columns = normalized_table_columns_map.get(normalized_table, [])
                if selected_columns:
                    replaced = True
                    qualifier = table_alias or resolved_table
                    for column_name in selected_columns:
                        expanded_expressions.append(exp.column(column_name, table=qualifier))
                    continue

            expanded_expressions.append(expression)
        if replaced and expanded_expressions:
            tree.set("expressions", expanded_expressions)
        normalized_sql = tree.sql(dialect="mysql").strip().rstrip(";")
        return normalized_sql + ";"

    @staticmethod
    def _is_statistical_query(sql_text: str, tree: exp.Expression | None) -> bool:
        """判断 SQL 是否为聚合/统计类查询（含 GROUP BY、HAVING 或 count/sum/avg/min/max）。"""
        if tree is not None:
            if tree.args.get("group") is not None or tree.args.get("having") is not None:
                return True
            if any(tree.find(func_type) is not None for func_type in (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)):
                return True
        return bool(
            re.search(
                r"\b(count|sum|avg|min|max)\s*\(|\bgroup\s+by\b|\bhaving\b",
                sql_text,
                flags=re.IGNORECASE,
            )
        )

    @staticmethod
    def _strip_top_level_limit(sql_text: str, tree: exp.Expression | None) -> str:
        """去掉顶层 LIMIT：统计类查询若被 LIMIT 截断会导致聚合结果不完整，故先剥离。"""
        if tree is not None and tree.args.get("limit") is not None:
            copied = tree.copy()
            copied.set("limit", None)
            return copied.sql(dialect="mysql").strip().rstrip(";")
        return re.sub(
            r"\s+limit\s+\d+\s*(,\s*\d+)?\s*$",
            "",
            sql_text,
            flags=re.IGNORECASE,
        ).strip()

    @classmethod
    def _ensure_limit(cls, sql: str) -> str:
        """明细查询自动补默认 LIMIT（防止全表拉取拖垮业务库）；统计类查询则保持不被 LIMIT 截断。"""
        sql_text = str(sql or "").strip().rstrip(";")
        if not sql_text:
            return f"SELECT 1 LIMIT {int(settings.TEXT2SQL_MAX_ROWS)};"
        tree: exp.Expression | None
        try:
            tree = parse_one(sql_text, read="mysql")
        except Exception:  # noqa: BLE001
            tree = None
        if cls._is_statistical_query(sql_text, tree):
            sql_without_limit = cls._strip_top_level_limit(sql_text, tree)
            return (sql_without_limit or sql_text).rstrip(";") + ";"
        if tree is not None and tree.args.get("limit") is not None:
            return tree.sql(dialect="mysql").strip().rstrip(";") + ";"
        if re.search(r"\blimit\b", sql_text, flags=re.IGNORECASE):
            return sql_text + ";"
        return f"{sql_text} LIMIT {int(settings.TEXT2SQL_MAX_ROWS)};"

    @staticmethod
    def _truncate_text(value: str | None, max_len: int) -> str:
        """日志用：截断过长文本，超出部分以省略号收尾。"""
        text = str(value or "")
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    @classmethod
    def _sample_rows_for_log(cls, rows: list[dict], max_rows: int = 3) -> list[dict]:
        """日志用：抽样若干结果行并逐字段截断，避免日志体积过大。"""
        sampled: list[dict] = []
        for row in rows[:max_rows]:
            sampled.append({str(k): cls._truncate_text(str(v), 80) for k, v in row.items()})
        return sampled

    def _get_llm_client(self, *, streaming: bool) -> ChatOpenAI | None:
        """按「当前生效的模型配置 + 温度」构建并缓存可复用的大模型客户端。

        以 base_url|model|api_key(|温度) 为缓存键：配置或温度变化才重建客户端，否则复用，
        避免每次调用都新建连接。流式与非流式各维护一份缓存。
        """
        from core.url_utils import normalize_llm_base_url
        from services.llm_service import llm_service

        cfg = llm_service._resolve_llm_config()
        if not cfg:
            return None

        base_url = str(cfg.get("base_url") or "").strip()
        api_key = str(cfg.get("api_key") or "").strip()
        model_name = str(cfg.get("model_name") or "").strip()
        if not (base_url and api_key and model_name):
            return None

        base_key = "|".join([base_url, model_name, api_key])
        if streaming:
            # 流式摘要始终使用确定性温度，不受 self-consistency 采样影响。
            temperature = 0.0
            current_key = base_key
            if self._streaming_model is not None and self._streaming_model_key == current_key:
                return self._streaming_model
        else:
            temperature = max(0.0, float(self._current_temperature))
            current_key = f"{base_key}|{temperature:.4f}"
            if self._model is not None and self._model_key == current_key:
                return self._model

        client = ChatOpenAI(
            base_url=normalize_llm_base_url(base_url),
            api_key=api_key,
            model=model_name,
            temperature=temperature,
            request_timeout=settings.LLM_TIMEOUT,
            streaming=streaming,
        )
        if streaming:
            self._streaming_model = client
            self._streaming_model_key = current_key
            return self._streaming_model

        self._model = client
        self._model_key = current_key
        return self._model

    def _get_model(self) -> ChatOpenAI | None:
        """获取非流式模型客户端（温度跟随 self-consistency 当前采样温度）。"""
        return self._get_llm_client(streaming=False)

    def _get_streaming_model(self) -> ChatOpenAI | None:
        """获取流式模型客户端（用于流式结果摘要，温度固定为 0 保证确定性）。"""
        return self._get_llm_client(streaming=True)

