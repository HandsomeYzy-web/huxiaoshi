from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_current_user_id
from core.database import get_db
from core.response import UnifiedResponse, success
from models.schemas.qa_schema import ChatAskRequest, ChatAskResponse, QAAskRequest, QAAskResponse
from services.qa_service import qa_service

router = APIRouter(prefix="/qa", tags=["QA"])


@router.post("/ask", response_model=UnifiedResponse[QAAskResponse])
async def ask_question(
    request: QAAskRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return success(data=qa_service.ask(db, request, user_id), message="Answered")


@router.post("/retrieve", response_model=UnifiedResponse[QAAskResponse])
async def retrieve_chunks(
    request: QAAskRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return success(data=qa_service.retrieve(db, request, user_id), message="Retrieved")


@router.post("/chat", response_model=UnifiedResponse[ChatAskResponse])
async def chat_with_all_knowledge_bases(
    request: ChatAskRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return success(data=qa_service.chat(db, request, user_id), message="Chat completed")
