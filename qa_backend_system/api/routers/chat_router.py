from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.dependencies import get_current_user, require_permission
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

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
    dependencies=[Depends(require_permission("chat.use"))],
)


@router.get("/sessions", response_model=UnifiedResponse[list[ChatSessionSummary]])
async def list_chat_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return success(data=chat_service.list_sessions(db, current_user.id), message="Fetched chat sessions")


@router.post("/sessions", response_model=UnifiedResponse[ChatSessionSummary])
async def create_chat_session(
    request: ChatSessionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=chat_service.create_session(db, request, current_user.id), message="Chat session created")


@router.get("/sessions/{session_id}", response_model=UnifiedResponse[ChatSessionDetail])
async def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=chat_service.get_session_detail(db, session_id, current_user.id), message="Fetched chat session")


@router.delete("/sessions/{session_id}", response_model=UnifiedResponse[None])
async def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat_service.delete_session(db, session_id, current_user.id)
    return success(data=None, message="Chat session deleted")


@router.patch("/sessions/{session_id}", response_model=UnifiedResponse[ChatSessionSummary])
async def rename_chat_session(
    session_id: int,
    request: ChatSessionRenameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=chat_service.rename_session(db, session_id, request, current_user.id), message="Chat session renamed")


@router.post("/sessions/{session_id}/messages", response_model=UnifiedResponse[ChatMessageCreateResponse])
async def append_chat_message(
    session_id: int,
    request: ChatMessageCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=chat_service.append_message(db, session_id, request, current_user.id), message="Message sent")


@router.post("/sessions/{session_id}/messages/stream")
async def append_chat_message_stream(
    session_id: int,
    request: ChatMessageCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return StreamingResponse(
        chat_service.stream_message(db, session_id, request, current_user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
