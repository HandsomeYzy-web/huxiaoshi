from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_id
from core.database import get_db
from core.exceptions import ResourceNotFoundError
from core.response import UnifiedResponse, success
from models.schemas.chat_schema import (
    ChatMessageCreateRequest,
    ChatMessageCreateResponse,
    ChatSessionCreateRequest,
    ChatSessionDetail,
    ChatSessionRenameRequest,
    ChatSessionSummary,
    ChatUploadResponse,
)
from services.chat_service import chat_service
from services.chat_upload_service import chat_upload_service

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/uploads", response_model=UnifiedResponse[ChatUploadResponse])
async def upload_chat_table(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    """上传表格文件用于聊天数据分析（短期存储，分析完成后自动删除）。"""
    content = await file.read()
    meta = chat_upload_service.save_upload(user_id, file.filename or "table.csv", content)
    return success(
        data=ChatUploadResponse(
            upload_id=meta["upload_id"],
            file_name=meta["file_name"],
            row_count=meta["row_count"],
            columns=meta["columns"],
            expires_in_seconds=meta["expires_in_seconds"],
        ),
        message="文件已上传（仅用于本次分析，分析后自动删除）",
    )


@router.delete("/uploads/{upload_id}", response_model=UnifiedResponse[None])
async def delete_chat_upload(
    upload_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """手动删除一次聊天上传（用户移除文件时调用）。"""
    if not chat_upload_service.delete_upload(upload_id, user_id=user_id):
        raise ResourceNotFoundError("上传文件不存在或已删除")
    return success(data=None, message="上传文件已删除")


@router.get("/sessions", response_model=UnifiedResponse[list[ChatSessionSummary]])
async def list_chat_sessions(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    return success(data=chat_service.list_sessions(db, user_id), message="Fetched chat sessions")


@router.post("/sessions", response_model=UnifiedResponse[ChatSessionSummary])
async def create_chat_session(
    request: ChatSessionCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return success(data=chat_service.create_session(db, request, user_id), message="Chat session created")


@router.get("/sessions/{session_id}", response_model=UnifiedResponse[ChatSessionDetail])
async def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return success(data=chat_service.get_session_detail(db, session_id, user_id), message="Fetched chat session")


@router.delete("/sessions/{session_id}", response_model=UnifiedResponse[None])
async def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    chat_service.delete_session(db, session_id, user_id)
    return success(data=None, message="Chat session deleted")


@router.patch("/sessions/{session_id}", response_model=UnifiedResponse[ChatSessionSummary])
async def rename_chat_session(
    session_id: int,
    request: ChatSessionRenameRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return success(data=chat_service.rename_session(db, session_id, request, user_id), message="Chat session renamed")


@router.post("/sessions/{session_id}/messages", response_model=UnifiedResponse[ChatMessageCreateResponse])
async def append_chat_message(
    session_id: int,
    request: ChatMessageCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return success(data=chat_service.append_message(db, session_id, request, user_id), message="Message sent")


@router.post("/sessions/{session_id}/messages/stream")
async def append_chat_message_stream(
    session_id: int,
    request: ChatMessageCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return StreamingResponse(
        chat_service.stream_message(db, session_id, request, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
