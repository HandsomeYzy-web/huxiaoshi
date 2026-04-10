"""
Chat Service — 三路由流式聊天管道。

SSE 事件协议:
  user_message  — 用户消息已保存
  session_info  — 会话更新（标题等）
  intent        — 意图分类结果 {intent, confidence, reason}
  status        — 当前处理步骤 {step, message}
  citations     — 引用文献列表（仅 doc_search）
  sql           — 生成的 SQL 语句（仅 data_query）
  sql_result    — SQL 查询结果 {columns, rows}（仅 data_query）
  delta         — LLM 流式文本块 {content}
  done          — 完成，含完整消息信息
  error         — 异常 {message}
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
from models.schemas.qa_schema import ChatAskRequest, CitationItem
from repositories.chat_repo import ChatRepo
from services.intent_service import (
    INTENT_CASUAL_CHAT,
    INTENT_DATA_QUERY,
    INTENT_DOC_SEARCH,
    intent_service,
)
from services.qa_service import qa_service


def _sse(event: str, data: dict | list | str) -> str:
    """Format a single SSE frame."""
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


class ChatService:
    # ── Session CRUD (unchanged) ─────────────────────────────────

    def list_sessions(self, db: Session, user_id: int) -> list[ChatSessionSummary]:
        repo = ChatRepo(db)
        sessions = repo.list_chat_sessions(user_id)
        return [ChatSessionSummary.model_validate(session) for session in sessions]

    def create_session(self, db: Session, request: ChatSessionCreateRequest, user_id: int) -> ChatSessionSummary:
        repo = ChatRepo(db)
        session = repo.create_chat_session(ChatSession(user_id=user_id, title=request.title.strip()))
        return ChatSessionSummary.model_validate(session)

    def delete_session(self, db: Session, session_id: int, user_id: int) -> None:
        deleted = ChatRepo(db).soft_delete_chat_session(session_id, user_id)
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

    # ── Non-streaming append (kept for backward compat) ──────────

    def append_message(self, db: Session, session_id: int, request: ChatMessageCreateRequest, user_id: int) -> ChatMessageCreateResponse:
        repo = ChatRepo(db)
        session = repo.get_chat_session(session_id, user_id)
        if not session:
            raise ResourceNotFoundError(f"聊天会话不存在或无权访问: session_id={session_id}")

        question = request.question.strip()
        user_message = repo.create_chat_message(
            ChatMessage(session_id=session.id, role="user", content=question, retrieved_count=0)
        )

        # 意图分类
        intent, confidence, reason = intent_service.classify(question)

        if intent == INTENT_CASUAL_CHAT:
            answer, model_used, citations_data, generated_sql, sql_result_json = self._handle_casual_chat(question)
        elif intent == INTENT_DATA_QUERY:
            answer, model_used, citations_data, generated_sql, sql_result_json = self._handle_data_query(question)
        else:
            answer, model_used, citations_data, generated_sql, sql_result_json = self._handle_doc_search(db, question)

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

        if session.title == "新对话":
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

    # ── Streaming entry point ────────────────────────────────────

    def stream_message(self, db: Session, session_id: int, request: ChatMessageCreateRequest, user_id: int) -> Generator[str, None, None]:
        """三路由流式消息，生成 SSE 格式数据流。"""
        repo = ChatRepo(db)
        session = repo.get_chat_session(session_id, user_id)
        if not session:
            raise ResourceNotFoundError(f"聊天会话不存在或无权访问: session_id={session_id}")

        question = request.question.strip()

        # 1. 保存用户消息
        user_message = repo.create_chat_message(
            ChatMessage(session_id=session.id, role="user", content=question, retrieved_count=0)
        )
        yield _sse("user_message", {
            "id": user_message.id,
            "content": user_message.content,
            "created_at": user_message.created_at.isoformat(),
        })

        # 2. 更新会话标题
        if session.title == "新对话":
            repo.update_chat_session_title(session.id, self._build_title(question))
        repo.touch_chat_session(session.id)
        refreshed_session = repo.get_chat_session(session.id, user_id)
        if refreshed_session is None:
            raise RuntimeError(f"会话 ID={session.id} 刷新失败")
        yield _sse("session_info", {
            "id": refreshed_session.id,
            "title": refreshed_session.title,
            "updated_at": refreshed_session.updated_at.isoformat(),
        })

        # 3. 意图分类
        yield _sse("status", {"step": "intent_classifying", "message": "正在分析问题意图..."})
        try:
            intent, confidence, reason = intent_service.classify(question)
        except Exception as e:
            logger.warning(f"Intent classification error: {e}")
            intent, confidence, reason = INTENT_DOC_SEARCH, 0.5, "分类异常，默认文档检索"

        yield _sse("intent", {"intent": intent, "confidence": confidence, "reason": reason})

        # 4. 路由到对应管道（使用 per-request ctx 避免并发冲突）
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

            else:  # doc_search
                for sse_frame in self._stream_doc_search(db, question, ctx):
                    yield sse_frame

            # 5. 保存助手消息
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

            # 6. 发送完成事件
            yield _sse("done", {
                "id": assistant_message.id,
                "content": ctx["full_answer"],
                "model_used": ctx["model_used"],
                "retrieved_count": len(ctx["citations_data"]),
                "intent": intent,
                "created_at": assistant_message.created_at.isoformat(),
            })

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield _sse("error", {"message": str(e)})
            raise

    # ── Streaming sub-pipelines ──────────────────────────────────

    def _stream_casual_chat(self, question: str, ctx: dict) -> Generator[str, None, None]:
        """闲聊路由：直接用 LLM 对话，无检索。"""
        from services.llm_service import llm_service

        yield _sse("status", {"step": "generating", "message": "正在生成回答..."})

        for chunk, is_model_info, model_name in llm_service.stream_casual_answer(question):
            if is_model_info:
                ctx["model_used"] = model_name
                continue
            if chunk:
                ctx["full_answer"] += chunk
                yield _sse("delta", {"content": chunk})

    def _stream_data_query(self, question: str, ctx: dict) -> Generator[str, None, None]:
        """数据查询路由：Text2SQL → 执行 → 流式总结。"""
        from services.text2sql_service import text2sql_service

        # Step 1: 生成 SQL
        yield _sse("status", {"step": "generating_sql", "message": "正在生成查询语句..."})
        try:
            sql = text2sql_service.generate_sql(question)
        except Exception as e:
            yield _sse("status", {"step": "sql_error", "message": f"SQL 生成失败: {e}"})
            ctx["full_answer"] = f"抱歉，无法为您的问题生成查询语句。错误: {e}"
            yield _sse("delta", {"content": ctx["full_answer"]})
            return

        ctx["generated_sql"] = sql
        yield _sse("sql", {"sql": sql})

        # Step 2: 校验 SQL
        is_valid, err_msg = text2sql_service.validate_sql(sql)
        if not is_valid:
            yield _sse("status", {"step": "sql_error", "message": f"SQL 安全校验未通过: {err_msg}"})
            ctx["full_answer"] = f"生成的 SQL 未通过安全校验: {err_msg}"
            yield _sse("delta", {"content": ctx["full_answer"]})
            return

        # Step 3: 执行 SQL
        yield _sse("status", {"step": "executing_sql", "message": "正在查询数据库..."})
        try:
            columns, rows = text2sql_service.execute_sql(sql)
        except Exception as e:
            yield _sse("status", {"step": "sql_error", "message": f"SQL 执行失败: {e}"})
            ctx["full_answer"] = f"查询执行出错: {e}"
            yield _sse("delta", {"content": ctx["full_answer"]})
            return

        result_data = {"columns": columns, "rows": rows}
        ctx["sql_result_json"] = json.dumps(result_data, ensure_ascii=False, default=str)
        yield _sse("sql_result", result_data)

        # Step 4: 流式总结结果
        yield _sse("status", {"step": "summarizing", "message": "正在分析查询结果..."})
        for chunk, is_model_info, model_name in text2sql_service.stream_summarize_result(question, sql, columns, rows):
            if is_model_info:
                ctx["model_used"] = model_name
                continue
            if chunk:
                ctx["full_answer"] += chunk
                yield _sse("delta", {"content": chunk})

    def _stream_doc_search(self, db: Session, question: str, ctx: dict) -> Generator[str, None, None]:
        """文档检索路由：RAG 检索 + 流式回答。"""
        yield _sse("status", {"step": "retrieving", "message": "正在检索知识库..."})

        chat_request = ChatAskRequest(question=question, top_k=settings.DEFAULT_RETRIEVAL_TOP_K)
        for chunk, is_model_info, model_name, citations in qa_service.stream_chat(db, request=chat_request):
            if citations:
                ctx["citations_data"] = [c.model_dump() for c in citations]
                yield _sse("citations", ctx["citations_data"])
                yield _sse("status", {"step": "generating", "message": "正在生成回答..."})
                continue

            if is_model_info:
                ctx["model_used"] = model_name
                continue

            if chunk:
                ctx["full_answer"] += chunk
                yield _sse("delta", {"content": chunk})

    # ── Non-streaming sub-pipelines ──────────────────────────────

    def _handle_casual_chat(self, question: str) -> tuple[str, str | None, list, str | None, str | None]:
        from services.llm_service import llm_service
        answer, model_used = llm_service.generate_casual_answer(question)
        return answer, model_used, [], None, None

    def _handle_data_query(self, question: str) -> tuple[str, str | None, list, str | None, str | None]:
        from services.text2sql_service import text2sql_service
        try:
            sql, summary, columns, rows = text2sql_service.query(question)
            result_json = json.dumps({"columns": columns, "rows": rows}, ensure_ascii=False, default=str)
            return summary, settings.EFFECTIVE_LLM_MODEL, [], sql, result_json
        except Exception as e:
            logger.error(f"Text2SQL pipeline error: {e}")
            return f"数据查询失败: {e}", None, [], None, None

    def _handle_doc_search(self, db: Session, question: str) -> tuple[str, str | None, list, str | None, str | None]:
        qa_result = qa_service.chat(db, request=ChatAskRequest(question=question, top_k=settings.DEFAULT_RETRIEVAL_TOP_K))
        citations_data = [item.model_dump() for item in qa_result.citations]
        return qa_result.answer, qa_result.model_used, citations_data, None, None

    # ── Helpers ───────────────────────────────────────────────────

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


chat_service = ChatService()
