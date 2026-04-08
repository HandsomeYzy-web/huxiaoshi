
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.dependencies import get_current_user
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.chat_schema import (
    ChatMessageCreateRequest,
    ChatMessageCreateResponse,
    ChatSessionCreateRequest,
    ChatSessionDetail,
    ChatSessionRenameRequest,
    ChatSessionSummary,
)
from services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.get("/sessions", response_model=UnifiedResponse[list[ChatSessionSummary]], summary="List chat sessions")
async def list_chat_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=chat_service.list_sessions(db, current_user.id), message="获取聊天会话成功")


@router.post("/sessions", response_model=UnifiedResponse[ChatSessionSummary], summary="Create chat session")
async def create_chat_session(
    request: ChatSessionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=chat_service.create_session(db, request, current_user.id), message="创建聊天会话成功")


@router.get("/sessions/{session_id}", response_model=UnifiedResponse[ChatSessionDetail], summary="Get chat session detail")
async def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=chat_service.get_session_detail(db, session_id, current_user.id), message="获取聊天详情成功")


@router.delete("/sessions/{session_id}", response_model=UnifiedResponse[None], summary="Delete chat session")
async def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat_service.delete_session(db, session_id, current_user.id)
    return success(data=None, message="会话已删除")


@router.patch("/sessions/{session_id}", response_model=UnifiedResponse[ChatSessionSummary], summary="Rename chat session")
async def rename_chat_session(
    session_id: int,
    request: ChatSessionRenameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=chat_service.rename_session(db, session_id, request, current_user.id), message="会话已重命名")


@router.post(
    "/sessions/{session_id}/messages",
    response_model=UnifiedResponse[ChatMessageCreateResponse],
    summary="Append chat message",
)
async def append_chat_message(
    session_id: int,
    request: ChatMessageCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(
        data=chat_service.append_message(db, session_id, request, current_user.id),
        message="发送消息成功",
    )


@router.post(
    "/sessions/{session_id}/messages/stream",
    summary="Append chat message with streaming response",
)
async def append_chat_message_stream(
    session_id: int,
    request: ChatMessageCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """流式聊天接口，使用 SSE 格式返回"""
    return StreamingResponse(
        chat_service.stream_message(db, session_id, request, current_user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
