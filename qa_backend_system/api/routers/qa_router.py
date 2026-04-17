from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_current_user, require_permission
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.qa_schema import ChatAskRequest, ChatAskResponse, QAAskRequest, QAAskResponse
from services.qa_service import qa_service

router = APIRouter(prefix="/qa", tags=["QA"])


@router.post("/ask", response_model=UnifiedResponse[QAAskResponse], dependencies=[Depends(require_permission("qa.run"))])
async def ask_question(
    request: QAAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=qa_service.ask(db, request, current_user.id), message="Answered")


@router.post("/retrieve", response_model=UnifiedResponse[QAAskResponse], dependencies=[Depends(require_permission("qa.run"))])
async def retrieve_chunks(
    request: QAAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=qa_service.retrieve(db, request, current_user.id), message="Retrieved")


@router.post("/chat", response_model=UnifiedResponse[ChatAskResponse], dependencies=[Depends(require_permission("chat.use"))])
async def chat_with_all_knowledge_bases(
    request: ChatAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success(data=qa_service.chat(db, request, current_user.id), message="Chat completed")
