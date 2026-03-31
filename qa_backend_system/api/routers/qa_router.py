from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_current_user
from core.database import get_db
from core.response import UnifiedResponse, success
from models.entities.user import User
from models.schemas.qa_schema import ChatAskRequest, ChatAskResponse, QAAskRequest, QAAskResponse
from services.qa_service import qa_service

router = APIRouter(prefix="/qa", tags=["QA"])


@router.post("/ask", response_model=UnifiedResponse[QAAskResponse], summary="Ask the knowledge base")
async def ask_question(
    request: QAAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = qa_service.ask(db, request)
    return success(data=result, message="")


@router.post("/retrieve", response_model=UnifiedResponse[QAAskResponse], summary="Retrieve citations only")
async def retrieve_chunks(
    request: QAAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = qa_service.retrieve(db, request)
    return success(data=result, message="检索测试成功")


@router.post("/chat", response_model=UnifiedResponse[ChatAskResponse], summary="Chat across all knowledge bases")
async def chat_with_all_knowledge_bases(
    request: ChatAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = qa_service.chat(db, request)
    return success(data=result, message="获取聊天对话成功")
