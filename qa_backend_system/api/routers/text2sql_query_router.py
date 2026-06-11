"""Text2SQL 查询路由（核心对外接口）。

承载用户「提问 → 出 SQL / 数据 / 回答」的主链路，提供四类接口：
    - /query            ：一次性查询，执行 SQL 并返回结果与自然语言回答；
    - /query/stream     ：同上，但以 SSE 流式逐阶段回推进度（路由/生成/执行/摘要）；
    - /query/feedback   ：用户对某条查询结果打满意度评分（高分回流为 few-shot 样例）；
    - /debug/generate(/stream)：仅生成并校验 SQL、不执行，用于调试预览。
    - /logs             ：查看本人最近的查询日志。
用户身份由上游统一认证平台经请求头注入；流式接口在子线程内跑流水线、用队列把进度桥接到 SSE 生成器。
具体业务逻辑委托给 facade_service / config_service / log_service。
"""

import json
from collections.abc import Generator
from queue import Queue
from threading import Thread

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_id
from core.config import settings
from core.database import SessionLocal, get_db
from core.exceptions import BusinessError
from core.response import UnifiedResponse, success
from models.schemas.text2sql_schema import (
    Text2SQLDebugGenerateResponse,
    Text2SQLFeedbackRequest,
    Text2SQLQueryLogItem,
    Text2SQLQueryRequest,
    Text2SQLQueryResponse,
)
from services.text2sql import config_service, facade_service, log_service

router = APIRouter(tags=["Text2SQL"])


def _sse(event: str, data: dict) -> str:
    """把事件名与数据序列化为一条 SSE 报文（event + data 两行，以空行结束）。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _build_query_response(payload: dict) -> Text2SQLQueryResponse:
    """把 facade 返回的查询载荷整理成对外响应模型（统一字段、补默认值）。"""
    return Text2SQLQueryResponse(
        sql=str(payload.get("sql") or ""),
        columns=list(payload.get("columns") or []),
        rows=list(payload.get("rows") or []),
        answer=str(payload.get("answer") or ""),
        row_count=len(list(payload.get("rows") or [])),
        repaired=bool(payload.get("repaired", False)),
        field_inference=list(payload.get("field_inference") or []),
        log_id=payload.get("log_id"),
        clarification=str(payload.get("clarification") or ""),
    )


def _build_debug_response(payload: dict) -> Text2SQLDebugGenerateResponse:
    """把 facade 调试载荷整理成调试响应模型（SQL、校验结论、路由命中表与打分等）。"""
    return Text2SQLDebugGenerateResponse(
        sql=str(payload.get("sql") or ""),
        validation_passed=bool(payload.get("validation_passed", False)),
        validation_message=str(payload.get("validation_message") or ""),
        route_mode=str(payload.get("mode") or ""),
        route_tables=list(payload.get("candidate_tables") or payload.get("selected_tables") or []),
        route_pool_tables=list(payload.get("route_pool_tables") or []),
        route_scores=dict(payload.get("route_scores") or {}),
        relation_hints=list(payload.get("relation_hints") or []),
        relation_guard_used=bool(payload.get("relation_guard_used", False)),
    )


@router.post(
    "/query",
    response_model=UnifiedResponse[Text2SQLQueryResponse],
)
async def text2sql_query(
    request: Text2SQLQueryRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """一次性查询：执行 SQL 并返回结果与自然语言回答（携带多轮历史以支持指代/追问）。"""
    if not settings.TEXT2SQL_ENABLED:
        raise BusinessError("Text2SQL is disabled")
    try:
        runtime_config = config_service.get_runtime_config(db, user_id=user_id)
        runtime_config["history"] = [turn.model_dump() for turn in request.history]
        payload = facade_service.query(
            request.question,
            db,
            runtime_config=runtime_config,
            user_id=user_id,
        )
        data = _build_query_response(payload)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Text2SQL query succeeded")


@router.post(
    "/query/feedback",
    response_model=UnifiedResponse[bool],
)
async def text2sql_query_feedback(
    request: Text2SQLFeedbackRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """记录用户对某条查询结果的满意度评分（1-5 星）；高分查询将被纳入 few-shot 示例池。"""
    try:
        updated = log_service.update_feedback(
            db,
            log_id=request.log_id,
            user_id=user_id,
            score=request.score,
        )
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    if not updated:
        raise BusinessError("反馈写入失败：日志不存在或无权限修改")
    return success(data=True, message="反馈已记录")


@router.post("/query/stream")
async def text2sql_query_stream(
    request: Text2SQLQueryRequest,
    user_id: int = Depends(get_current_user_id),
):
    """流式查询：在子线程跑流水线，通过队列把各阶段进度桥接为 SSE 事件实时回推前端。"""
    if not settings.TEXT2SQL_ENABLED:
        raise BusinessError("Text2SQL is disabled")

    def event_stream() -> Generator[str, None, None]:
        # 进度事件队列：worker 线程产出 (event, data)，主协程消费并以 SSE 下发；None 为结束哨兵。
        queue: Queue[tuple[str, dict] | None] = Queue()

        def emit_progress(event: str, data: dict) -> None:
            queue.put((event, data))

        def worker() -> None:
            # 子线程独立开 DB 会话跑完整查询，进度通过 emit_progress 回灌队列。
            db = SessionLocal()
            try:
                runtime_config = config_service.get_runtime_config(db, user_id=user_id)
                runtime_config["history"] = [turn.model_dump() for turn in request.history]
                emit_progress("status", {"step": "routing", "message": "正在选择候选表..."})
                payload = facade_service.query(
                    request.question,
                    db,
                    runtime_config=runtime_config,
                    user_id=user_id,
                    progress_callback=emit_progress,
                )
                emit_progress("status", {"step": "completed", "message": "查询完成"})
                emit_progress("done", _build_query_response(payload).model_dump())
            except (ValueError, RuntimeError, BusinessError) as exc:
                emit_progress("error", {"message": str(exc)})
            except Exception as exc:  # noqa: BLE001
                emit_progress("error", {"message": str(exc)})
            finally:
                db.close()
                queue.put(None)

        Thread(target=worker, daemon=True).start()

        while True:
            item = queue.get()
            if item is None:
                break
            event, data = item
            yield _sse(event, data)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/debug/generate",
    response_model=UnifiedResponse[Text2SQLDebugGenerateResponse],
)
async def text2sql_debug_generate(
    request: Text2SQLQueryRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """调试生成：仅路由 + 生成 + 校验，不执行 SQL，用于预览模型生成的 SQL 与路由情况。"""
    if not settings.TEXT2SQL_ENABLED:
        raise BusinessError("Text2SQL is disabled")
    try:
        runtime_config = config_service.get_runtime_config(db, user_id=user_id)
        runtime_config["history"] = [turn.model_dump() for turn in request.history]
        payload = facade_service.debug_generate(
            request.question,
            db,
            runtime_config=runtime_config,
            user_id=user_id,
        )
        data = _build_debug_response(payload)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=data, message="Generated SQL for debug")


@router.post("/debug/generate/stream")
async def text2sql_debug_generate_stream(
    request: Text2SQLQueryRequest,
    user_id: int = Depends(get_current_user_id),
):
    """流式调试生成：与 /debug/generate 相同，但逐阶段以 SSE 回推生成进度。"""
    if not settings.TEXT2SQL_ENABLED:
        raise BusinessError("Text2SQL is disabled")

    def event_stream() -> Generator[str, None, None]:
        queue: Queue[tuple[str, dict] | None] = Queue()

        def emit_progress(event: str, data: dict) -> None:
            queue.put((event, data))

        def worker() -> None:
            db = SessionLocal()
            try:
                runtime_config = config_service.get_runtime_config(db, user_id=user_id)
                runtime_config["history"] = [turn.model_dump() for turn in request.history]
                emit_progress("status", {"step": "routing", "message": "正在选择候选表..."})
                payload = facade_service.debug_generate(
                    request.question,
                    db,
                    runtime_config=runtime_config,
                    user_id=user_id,
                    progress_callback=emit_progress,
                )
                emit_progress("status", {"step": "completed", "message": "SQL 生成完成"})
                emit_progress("done", _build_debug_response(payload).model_dump())
            except (ValueError, RuntimeError, BusinessError) as exc:
                emit_progress("error", {"message": str(exc)})
            except Exception as exc:  # noqa: BLE001
                emit_progress("error", {"message": str(exc)})
            finally:
                db.close()
                queue.put(None)

        Thread(target=worker, daemon=True).start()

        while True:
            item = queue.get()
            if item is None:
                break
            event, data = item
            yield _sse(event, data)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/logs",
    response_model=UnifiedResponse[list[Text2SQLQueryLogItem]],
)
async def get_text2sql_logs(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """查看当前用户最近的查询日志（按时间倒序，最多 limit 条）。"""
    try:
        logs = log_service.list_logs(db, user_id=user_id, limit=limit)
    except (ValueError, RuntimeError) as exc:
        raise BusinessError(str(exc)) from exc
    return success(data=logs, message="Fetched Text2SQL logs")
