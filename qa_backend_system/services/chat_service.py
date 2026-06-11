"""
Chat Service — 多链路流式聊天管道。

按用户选择的模式（或自动意图分类）分流：
- casual_chat: 闲聊
- doc_search: 知识库检索（mode=docs 或 auto 判定）
- data_query: 数据查询，走 text2SQL 链路（mode=data 或 auto 判定）
- file_analysis: 上传表格分析（mode=file，短期存储、分析后删除）

同时保持当前实现不再跨线程共享 SQLAlchemy Session。
"""

import json
from collections.abc import Generator
from queue import Queue
from threading import Thread

from sqlalchemy.orm import Session

from core.config import settings
from core.database import SessionLocal
from core.exceptions import BusinessError, ResourceNotFoundError
from core.logger import logger
from models.entities import ChatMessage, ChatSession
from models.schemas.chat_schema import (
    ChatDocumentItem,
    ChatMessageCreateRequest,
    ChatMessageCreateResponse,
    ChatMessageResponse,
    ChatSessionCreateRequest,
    ChatSessionDetail,
    ChatSessionRenameRequest,
    ChatSessionSummary,
)
from models.schemas.qa_schema import CitationItem
from repositories.chat_repo import ChatRepo
from services.intent_service import (
    INTENT_CASUAL_CHAT,
    INTENT_DATA_QUERY,
    INTENT_DOC_SEARCH,
    intent_service,
)
from services.qa_service import qa_service

# 上传表格分析的伪意图（不参与自动分类，仅 mode=file 触发）
INTENT_FILE_ANALYSIS = "file_analysis"

DEFAULT_SESSION_TITLE = ChatSessionCreateRequest.model_fields["title"].default


def _sse(event: str, data: dict | list | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


class ChatService:
    def list_sessions(self, db: Session, user_id: int) -> list[ChatSessionSummary]:
        repo = ChatRepo(db)
        sessions = repo.list_chat_sessions(user_id)
        return [ChatSessionSummary.model_validate(session) for session in sessions]

    def create_session(self, db: Session, request: ChatSessionCreateRequest, user_id: int) -> ChatSessionSummary:
        repo = ChatRepo(db)
        session = repo.create_chat_session(ChatSession(user_id=user_id, title=request.title.strip()))
        return ChatSessionSummary.model_validate(session)

    def delete_session(self, db: Session, session_id: int, user_id: int) -> None:
        deleted = ChatRepo(db).delete_chat_session(session_id, user_id)
        if not deleted:
            raise ResourceNotFoundError(f"聊天会话不存在或无权操作: session_id={session_id}")

    def rename_session(self, db: Session, session_id: int, request: ChatSessionRenameRequest, user_id: int) -> ChatSessionSummary:
        session = ChatRepo(db).rename_chat_session(session_id, user_id, request.title)
        if not session:
            raise ResourceNotFoundError(f"聊天会话不存在或无权操作: session_id={session_id}")
        return ChatSessionSummary.model_validate(session)

    def get_session_detail(self, db: Session, session_id: int, user_id: int) -> ChatSessionDetail:
        repo = ChatRepo(db)
        session = repo.get_chat_session(session_id, user_id)
        if not session:
            raise ResourceNotFoundError(f"聊天会话不存在或无权访问: session_id={session_id}")

        messages = repo.list_chat_messages(session_id)
        return ChatSessionDetail(
            session=ChatSessionSummary.model_validate(session),
            messages=[self._to_message_response(message) for message in messages],
            involved_documents=self._collect_documents(messages),
        )

    def append_message(self, db: Session, session_id: int, request: ChatMessageCreateRequest, user_id: int) -> ChatMessageCreateResponse:
        repo = ChatRepo(db)
        session = repo.get_chat_session(session_id, user_id)
        if not session:
            raise ResourceNotFoundError(f"聊天会话不存在或无权访问: session_id={session_id}")

        question = request.question.strip()
        user_message = repo.create_chat_message(
            ChatMessage(session_id=session.id, role="user", content=question, retrieved_count=0)
        )

        # 加载最近对话历史，用于 query 改写
        all_messages = repo.list_chat_messages(session.id)
        recent_history = self._extract_history_pairs(all_messages)

        intent, _, _ = self._resolve_intent(question, request.mode)
        if intent == INTENT_CASUAL_CHAT:
            answer, model_used, citations_data, generated_sql, sql_result_json = self._handle_casual_chat(question)
        elif intent == INTENT_FILE_ANALYSIS:
            answer, model_used, citations_data, generated_sql, sql_result_json = self._handle_file_analysis(
                question, request.upload_id, user_id
            )
        elif intent == INTENT_DATA_QUERY:
            answer, model_used, citations_data, generated_sql, sql_result_json = self._handle_data_query(
                db, question, user_id, data_history=self._extract_data_history(all_messages)
            )
        else:
            answer, model_used, citations_data, generated_sql, sql_result_json = self._handle_doc_search(
                db, question, user_id, history=recent_history
            )

        assistant_message = repo.create_chat_message(
            ChatMessage(
                session_id=session.id,
                role="assistant",
                content=answer,
                model_used=model_used,
                retrieved_count=len(citations_data),
                citations_json=json.dumps(citations_data, ensure_ascii=False) if citations_data else None,
                intent=intent,
                generated_sql=generated_sql,
                sql_result_json=sql_result_json,
            )
        )

        if session.title == DEFAULT_SESSION_TITLE:
            repo.update_chat_session_title(session.id, self._build_title(question))
        repo.touch_chat_session(session.id)
        refreshed_session = repo.get_chat_session(session.id, user_id)
        messages = repo.list_chat_messages(session.id)
        return ChatMessageCreateResponse(
            session=ChatSessionSummary.model_validate(refreshed_session),
            user_message=self._to_message_response(user_message),
            assistant_message=self._to_message_response(assistant_message),
            involved_documents=self._collect_documents(messages),
        )

    def stream_message(self, db: Session, session_id: int, request: ChatMessageCreateRequest, user_id: int) -> Generator[str, None, None]:
        repo = ChatRepo(db)
        session = repo.get_chat_session(session_id, user_id)
        if not session:
            raise ResourceNotFoundError(f"聊天会话不存在或无权访问: session_id={session_id}")

        question = request.question.strip()
        user_message = repo.create_chat_message(
            ChatMessage(session_id=session.id, role="user", content=question, retrieved_count=0)
        )
        yield _sse(
            "user_message",
            {
                "id": user_message.id,
                "content": user_message.content,
                "created_at": user_message.created_at.isoformat(),
            },
        )

        if session.title == DEFAULT_SESSION_TITLE:
            repo.update_chat_session_title(session.id, self._build_title(question))
        repo.touch_chat_session(session.id)
        refreshed_session = repo.get_chat_session(session.id, user_id)
        yield _sse(
            "session_info",
            {
                "id": refreshed_session.id,
                "title": refreshed_session.title,
                "updated_at": refreshed_session.updated_at.isoformat(),
            },
        )

        # 加载最近对话历史，用于 query 改写
        all_messages = repo.list_chat_messages(session.id)
        recent_history = self._extract_history_pairs(all_messages)

        if request.mode == "auto":
            yield _sse("status", {"step": "intent_classifying", "message": "正在分析问题意图..."})
        intent, confidence, reason = self._resolve_intent(question, request.mode)
        yield _sse("intent", {"intent": intent, "confidence": confidence, "reason": reason})
        ctx: dict = {
            "full_answer": "",
            "model_used": None,
            "citations_data": [],
            "generated_sql": None,
            "sql_result_json": None,
        }

        try:
            if intent == INTENT_CASUAL_CHAT:
                for sse_frame in self._stream_casual_chat(question, ctx):
                    yield sse_frame
            elif intent == INTENT_FILE_ANALYSIS:
                for sse_frame in self._stream_file_analysis(question, request.upload_id, user_id, ctx):
                    yield sse_frame
            elif intent == INTENT_DATA_QUERY:
                for sse_frame in self._stream_data_query(
                    question, user_id, ctx, data_history=self._extract_data_history(all_messages)
                ):
                    yield sse_frame
            else:
                for sse_frame in self._stream_doc_search(db, question, user_id, ctx, history=recent_history):
                    yield sse_frame

            assistant_message = repo.create_chat_message(
                ChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=ctx["full_answer"],
                    model_used=ctx["model_used"],
                    retrieved_count=len(ctx["citations_data"]),
                    citations_json=json.dumps(ctx["citations_data"], ensure_ascii=False) if ctx["citations_data"] else None,
                    intent=intent,
                    generated_sql=ctx["generated_sql"],
                    sql_result_json=ctx["sql_result_json"],
                )
            )

            yield _sse(
                "done",
                {
                    "id": assistant_message.id,
                    "content": ctx["full_answer"],
                    "model_used": ctx["model_used"],
                    "retrieved_count": len(ctx["citations_data"]),
                    "intent": intent,
                    "created_at": assistant_message.created_at.isoformat(),
                },
            )
        except Exception as exc:
            logger.error(f"Stream error: {exc}")
            yield _sse("error", {"message": str(exc)})
            raise

    def _resolve_intent(self, question: str, mode: str) -> tuple[str, float, str]:
        """按用户选择的模式确定链路；mode=auto 时走 LLM 意图分类。"""
        if mode == "docs":
            return INTENT_DOC_SEARCH, 1.0, "用户指定查文档"
        if mode == "data":
            if not settings.TEXT2SQL_ENABLED:
                return INTENT_DOC_SEARCH, 1.0, "Text2SQL 未启用，回退为文档检索"
            return INTENT_DATA_QUERY, 1.0, "用户指定查数据"
        if mode == "file":
            return INTENT_FILE_ANALYSIS, 1.0, "上传表格分析"

        intent, confidence, reason = self._classify_intent(question)
        if intent == INTENT_DATA_QUERY and not settings.TEXT2SQL_ENABLED:
            return INTENT_DOC_SEARCH, confidence, "Text2SQL 未启用，回退为文档检索"
        return intent, confidence, reason

    def _classify_intent(self, question: str) -> tuple[str, float, str]:
        try:
            return intent_service.classify(question)
        except Exception as exc:
            logger.warning(f"Intent classification error: {exc}")
            return INTENT_DOC_SEARCH, 0.5, "分类异常，默认文档检索"

    def _handle_casual_chat(self, question: str) -> tuple[str, str | None, list, str | None, str | None]:
        from services.llm_service import llm_service

        if llm_service.model is None:
            return "LLM 未配置，无法生成回答。", None, [], None, None

        try:
            chain = llm_service.merged_prompt | llm_service.model | llm_service.output_parser
            answer = chain.invoke(
                {
                    "question": question,
                    "sources_block": llm_service._build_sources_block(None, None, None, None),
                }
            )
            return answer, llm_service._resolved_model_name, [], None, None
        except Exception as exc:
            logger.error(f"Casual chat pipeline error: {exc}")
            return f"生成回答失败: {exc}", None, [], None, None

    def _handle_doc_search(
        self, db: Session, question: str, user_id: int, history: list[tuple[str, str]] | None = None
    ) -> tuple[str, str | None, list, str | None, str | None]:
        from services.llm_service import llm_service
        rewritten = llm_service.rewrite_query(question, history or [])
        retrieve_result = qa_service.retrieve_for_chat_with_context(
            db, question, rewritten, user_id, settings.DEFAULT_RETRIEVAL_TOP_K
        )
        citations = retrieve_result["citations"]
        contexts = retrieve_result["contexts"]
        answer, model_used = llm_service.generate_answer(question, contexts)
        return answer, model_used, [c.model_dump() for c in citations], None, None

    # ------------------------------------------------------------------
    # 数据查询（text2SQL 链路）
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_data_history(messages: list[ChatMessage]) -> list[dict]:
        """提取最近 3 轮数据查询对话（text2SQL 多轮上下文格式：question/sql/answer）。"""
        turns: list[dict] = []
        prev_user: str | None = None
        for msg in messages:
            if msg.role == "user":
                prev_user = msg.content
            elif msg.role == "assistant" and prev_user is not None:
                if msg.intent == INTENT_DATA_QUERY:
                    turns.append(
                        {
                            "question": prev_user[:4000],
                            "sql": (msg.generated_sql or "")[:8000],
                            "answer": (msg.content or "")[:4000],
                        }
                    )
                prev_user = None
        return turns[-3:]

    @staticmethod
    def _run_text2sql_query(db: Session, question: str, user_id: int, data_history: list[dict], progress_callback=None) -> dict:
        """调用 text2SQL facade 执行一次数据查询，返回原始 payload。"""
        from services.text2sql import config_service, facade_service

        runtime_config = config_service.get_runtime_config(db, user_id=user_id)
        runtime_config["history"] = data_history or []
        return facade_service.query(
            question,
            db,
            runtime_config=runtime_config,
            user_id=user_id,
            progress_callback=progress_callback,
        )

    @staticmethod
    def _apply_text2sql_payload(ctx: dict, payload: dict) -> None:
        """把 facade 返回载荷写入流式上下文（SQL、结果集、回答）。"""
        sql = str(payload.get("sql") or "")
        columns = list(payload.get("columns") or [])
        rows = list(payload.get("rows") or [])
        clarification = str(payload.get("clarification") or "")
        answer = clarification or str(payload.get("answer") or "")

        ctx["generated_sql"] = sql or None
        if columns:
            ctx["sql_result_json"] = json.dumps({"columns": columns, "rows": rows}, ensure_ascii=False)
        ctx["full_answer"] = answer or "查询完成，但未生成回答。"

    def _handle_data_query(
        self, db: Session, question: str, user_id: int, data_history: list[dict] | None = None
    ) -> tuple[str, str | None, list, str | None, str | None]:
        from services.llm_service import llm_service

        try:
            payload = self._run_text2sql_query(db, question, user_id, data_history or [])
        except Exception as exc:
            logger.error(f"Chat data query failed: {exc}")
            return f"数据查询失败: {exc}", None, [], None, None

        ctx: dict = {"full_answer": "", "generated_sql": None, "sql_result_json": None}
        self._apply_text2sql_payload(ctx, payload)
        return (
            ctx["full_answer"],
            llm_service._resolved_model_name,
            [],
            ctx["generated_sql"],
            ctx["sql_result_json"],
        )

    def _stream_data_query(
        self, question: str, user_id: int, ctx: dict, data_history: list[dict] | None = None
    ) -> Generator[str, None, None]:
        """流式数据查询：facade 在子线程内跑（独立 DB 会话），进度经队列桥接为 SSE。"""
        from services.llm_service import llm_service

        queue: Queue[tuple[str, dict] | None] = Queue()

        def emit_progress(event: str, data: dict) -> None:
            queue.put((event, data))

        def worker() -> None:
            worker_db = SessionLocal()
            try:
                payload = self._run_text2sql_query(
                    worker_db, question, user_id, data_history or [], progress_callback=emit_progress
                )
                queue.put(("__done__", payload))
            except Exception as exc:  # noqa: BLE001
                queue.put(("__error__", {"message": str(exc)}))
            finally:
                worker_db.close()
                queue.put(None)

        yield _sse("status", {"step": "routing", "message": "正在分析数据查询..."})
        Thread(target=worker, daemon=True).start()

        while True:
            item = queue.get()
            if item is None:
                break
            event, data = item
            if event == "__done__":
                self._apply_text2sql_payload(ctx, data)
                ctx["model_used"] = llm_service._resolved_model_name
                if ctx["sql_result_json"]:
                    yield _sse("sql_result", json.loads(ctx["sql_result_json"]))
                if ctx["full_answer"]:
                    yield _sse("delta", {"content": ctx["full_answer"]})
            elif event == "__error__":
                ctx["full_answer"] = f"数据查询失败: {data.get('message', '未知错误')}"
                yield _sse("delta", {"content": ctx["full_answer"]})
            elif event == "status":
                yield _sse("status", data)
            # facade 的其他进度事件（如 sql_generated）不直接透传，避免前端无法识别

    # ------------------------------------------------------------------
    # 上传表格分析（短期存储，分析后删除）
    # ------------------------------------------------------------------

    def _handle_file_analysis(
        self, question: str, upload_id: str | None, user_id: int
    ) -> tuple[str, str | None, list, str | None, str | None]:
        ctx: dict = {
            "full_answer": "",
            "model_used": None,
            "citations_data": [],
            "generated_sql": None,
            "sql_result_json": None,
        }
        for _ in self._stream_file_analysis(question, upload_id, user_id, ctx):
            pass
        return ctx["full_answer"], ctx["model_used"], [], ctx["generated_sql"], ctx["sql_result_json"]

    def _stream_file_analysis(
        self, question: str, upload_id: str | None, user_id: int, ctx: dict
    ) -> Generator[str, None, None]:
        from services.chat_upload_service import chat_upload_service

        if not upload_id:
            ctx["full_answer"] = "请先上传要分析的表格文件（支持 csv/xlsx/xls）。"
            yield _sse("delta", {"content": ctx["full_answer"]})
            return

        try:
            for event, data in chat_upload_service.analyze_stream(upload_id, user_id, question):
                if event == "status":
                    yield _sse("status", data)
                elif event == "sql_result":
                    ctx["generated_sql"] = data.get("sql")
                    result = {"columns": data.get("columns", []), "rows": data.get("rows", [])}
                    ctx["sql_result_json"] = json.dumps(result, ensure_ascii=False)
                    yield _sse("sql_result", result)
                elif event == "model":
                    ctx["model_used"] = data.get("model_used")
                elif event == "delta":
                    chunk = data.get("content", "")
                    if chunk:
                        ctx["full_answer"] += chunk
                        yield _sse("delta", {"content": chunk})
        except BusinessError as exc:
            ctx["full_answer"] = ctx["full_answer"] or f"表格分析失败: {exc.message}"
            yield _sse("delta", {"content": f"表格分析失败: {exc.message}"})
        except Exception as exc:  # noqa: BLE001
            logger.error(f"File analysis failed: {exc}")
            ctx["full_answer"] = ctx["full_answer"] or f"表格分析失败: {exc}"
            yield _sse("delta", {"content": f"表格分析失败: {exc}"})

    def _stream_casual_chat(self, question: str, ctx: dict) -> Generator[str, None, None]:
        from services.llm_service import llm_service

        yield _sse("status", {"step": "generating", "message": "正在生成回答..."})
        for chunk, is_model_info, model_name in llm_service.stream_merged_answer(question):
            if is_model_info:
                ctx["model_used"] = model_name
                continue
            if chunk:
                ctx["full_answer"] += chunk
                yield _sse("delta", {"content": chunk})

    def _stream_doc_search(
        self, db: Session, question: str, user_id: int, ctx: dict, history: list[tuple[str, str]] | None = None
    ) -> Generator[str, None, None]:
        from services.llm_service import llm_service

        yield _sse("status", {"step": "rewriting_query", "message": "正在改写问题..."})
        rewritten = llm_service.rewrite_query(question, history or [])

        yield _sse("status", {"step": "retrieving", "message": "正在检索知识库..."})
        retrieve_result = qa_service.retrieve_for_chat_with_context(
            db, question, rewritten, user_id, settings.DEFAULT_RETRIEVAL_TOP_K
        )
        citations = retrieve_result["citations"]
        contexts = retrieve_result["contexts"]
        ctx["citations_data"] = [c.model_dump() for c in citations]
        if ctx["citations_data"]:
            yield _sse("citations", ctx["citations_data"])

        yield _sse("status", {"step": "generating", "message": "正在生成回答..."})
        for chunk, is_model_info, model_name in llm_service.stream_answer(question, contexts):
            if is_model_info:
                ctx["model_used"] = model_name
                continue
            if chunk:
                ctx["full_answer"] += chunk
                yield _sse("delta", {"content": chunk})

    def _to_message_response(self, message: ChatMessage) -> ChatMessageResponse:
        citations = []
        if message.citations_json:
            citations = [CitationItem.model_validate(item) for item in json.loads(message.citations_json)]
        return ChatMessageResponse(
            id=message.id,
            session_id=message.session_id,
            role=message.role,
            content=message.content,
            model_used=message.model_used,
            retrieved_count=message.retrieved_count,
            citations=citations,
            intent=message.intent,
            generated_sql=message.generated_sql,
            sql_result_json=message.sql_result_json,
            created_at=message.created_at,
        )

    def _collect_documents(self, messages: list[ChatMessage]) -> list[ChatDocumentItem]:
        seen: set[tuple[int, int]] = set()
        documents: list[ChatDocumentItem] = []
        for message in messages:
            if not message.citations_json:
                continue
            for item in json.loads(message.citations_json):
                key = (int(item["kb_id"]), int(item["file_id"]))
                if key in seen:
                    continue
                seen.add(key)
                documents.append(
                    ChatDocumentItem(
                        kb_id=int(item["kb_id"]),
                        kb_name=item["kb_name"],
                        file_id=int(item["file_id"]),
                        file_name=item["file_name"],
                    )
                )
        return documents

    def _build_title(self, question: str) -> str:
        return question[:24] + ("..." if len(question) > 24 else "")

    @staticmethod
    def _extract_history_pairs(messages: list[ChatMessage]) -> list[tuple[str, str]]:
        """从消息列表中提取最近 3 轮用户-助手对话，用于 query 改写。"""
        pairs: list[tuple[str, str]] = []
        prev_user: str | None = None
        for msg in messages:
            if msg.role == "user":
                prev_user = msg.content
            elif msg.role == "assistant" and prev_user is not None:
                pairs.append((prev_user, msg.content))
                prev_user = None
        return pairs[-3:]


chat_service = ChatService()
