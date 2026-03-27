from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.response import UnifiedResponse, success
from models.schemas.chat_schema import (
    ChatMessageCreateRequest,
    ChatMessageCreateResponse,
    ChatSessionCreateRequest,
    ChatSessionDetail,
    ChatSessionSummary,
)
from services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.get("/sessions", response_model=UnifiedResponse[list[ChatSessionSummary]], summary="List chat sessions")
async def list_chat_sessions(db: Session = Depends(get_db)):
    return success(data=chat_service.list_sessions(db), message="获取聊天会话成功")


@router.post("/sessions", response_model=UnifiedResponse[ChatSessionSummary], summary="Create chat session")
async def create_chat_session(request: ChatSessionCreateRequest, db: Session = Depends(get_db)):
    return success(data=chat_service.create_session(db, request), message="创建聊天会话成功")


@router.get("/sessions/{session_id}", response_model=UnifiedResponse[ChatSessionDetail], summary="Get chat session detail")
async def get_chat_session(session_id: int, db: Session = Depends(get_db)):
    try:
        return success(data=chat_service.get_session_detail(db, session_id), message="获取聊天详情成功")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/sessions/{session_id}/messages",
    response_model=UnifiedResponse[ChatMessageCreateResponse],
    summary="Append chat message",
)
async def append_chat_message(session_id: int, request: ChatMessageCreateRequest, db: Session = Depends(get_db)):
    try:
        return success(data=chat_service.append_message(db, session_id, request), message="发送消息成功")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
