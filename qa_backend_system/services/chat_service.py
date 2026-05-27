"""
Chat Service — 三路由流式聊天管道。

恢复按意图分流：
- casual_chat: 闲聊
- data_query: Text2SQL
- doc_search: 知识库检索

同时保持当前实现不再跨线程共享 SQLAlchemy Session。
"""

import json
from collections.abc import Generator

from sqlalchemy.orm import Session

from core.config import settings
from core.exceptions import ResourceNotFoundError
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

        intent, _, _ = self._classify_intent(question)
        if intent == INTENT_CASUAL_CHAT:
            answer, model_used, citations_data, generated_sql, sql_result_json = self._handle_casual_chat(question)
        elif intent == INTENT_DATA_QUERY:
            answer, model_used, citations_data, generated_sql, sql_result_json = self._handle_data_query(question)
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

        yield _sse("status", {"step": "intent_classifying", "message": "正在分析问题意图..."})
        intent, confidence, reason = self._classify_intent(question)
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
            elif intent == INTENT_DATA_QUERY:
                for sse_frame in self._stream_data_query(question, ctx):
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

    def _handle_data_query(self, question: str) -> tuple[str, str | None, list, str | None, str | None]:
        from services.llm_service import llm_service
        from services.text2sql_service import text2sql_service

        try:
            sql, summary, columns, rows = text2sql_service.query(question)
            result_json = json.dumps({"columns": columns, "rows": rows}, ensure_ascii=False, default=str)
            cfg = llm_service._resolve_llm_config()
            model_used = cfg["model_name"] if cfg else None
            return summary, model_used, [], sql, result_json
        except Exception as exc:
            logger.error(f"Text2SQL pipeline error: {exc}")
            return f"数据查询失败: {exc}", None, [], None, None

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

    def _stream_data_query(self, question: str, ctx: dict) -> Generator[str, None, None]:
        from services.text2sql_service import text2sql_service

        yield _sse("status", {"step": "generating_sql", "message": "正在生成查询语句..."})
        try:
            sql = text2sql_service.generate_sql(question)
        except Exception as exc:
            yield _sse("status", {"step": "sql_error", "message": f"SQL 生成失败: {exc}"})
            ctx["full_answer"] = f"抱歉，无法为您的问题生成查询语句。错误: {exc}"
            yield _sse("delta", {"content": ctx["full_answer"]})
            return

        ctx["generated_sql"] = sql
        is_valid, err_msg = text2sql_service.validate_sql(sql)
        if not is_valid:
            yield _sse("status", {"step": "sql_error", "message": f"SQL 安全校验未通过: {err_msg}"})
            ctx["full_answer"] = f"生成的 SQL 未通过安全校验: {err_msg}"
            yield _sse("delta", {"content": ctx["full_answer"]})
            return

        yield _sse("status", {"step": "executing_sql", "message": "正在查询数据库..."})
        try:
            columns, rows = text2sql_service.execute_sql(sql)
        except Exception as exc:
            yield _sse("status", {"step": "sql_error", "message": f"SQL 执行失败: {exc}"})
            ctx["full_answer"] = f"查询执行出错: {exc}"
            yield _sse("delta", {"content": ctx["full_answer"]})
            return

        result_data = {"columns": columns, "rows": rows}
        ctx["sql_result_json"] = json.dumps(result_data, ensure_ascii=False, default=str)
        yield _sse("sql_result", result_data)

        yield _sse("status", {"step": "summarizing", "message": "正在分析查询结果..."})
        for chunk, is_model_info, model_name in text2sql_service.stream_summarize_result(
            question, sql, columns, rows
        ):
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
