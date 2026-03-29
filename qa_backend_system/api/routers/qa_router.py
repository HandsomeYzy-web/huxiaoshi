from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.response import UnifiedResponse, success
from models.schemas.qa_schema import ChatAskRequest, ChatAskResponse, QAAskRequest, QAAskResponse
from services.qa_service import qa_service

router = APIRouter(prefix="/qa", tags=["QA"])


@router.post("/ask", response_model=UnifiedResponse[QAAskResponse], summary="Ask the knowledge base")
async def ask_question(request: QAAskRequest, db: Session = Depends(get_db)):
    try:
        result = qa_service.ask(db, request)
        return success(data=result, message="")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/retrieve", response_model=UnifiedResponse[QAAskResponse], summary="Retrieve citations only")
async def retrieve_chunks(request: QAAskRequest, db: Session = Depends(get_db)):
    try:
        result = qa_service.retrieve(db, request)
        return success(data=result, message="检索测试成功")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/chat", response_model=UnifiedResponse[ChatAskResponse], summary="Chat across all knowledge bases")
async def chat_with_all_knowledge_bases(request: ChatAskRequest, db: Session = Depends(get_db)):
    try:
        result = qa_service.chat(db, request)
        return success(data=result, message="获取聊天对话成功")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
