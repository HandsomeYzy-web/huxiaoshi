from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.response import UnifiedResponse, success
from models.schemas.qa_schema import QAAskRequest, QAAskResponse
from services.qa_service import qa_service

router = APIRouter(prefix="/qa", tags=["QA"])


@router.post("/ask", response_model=UnifiedResponse[QAAskResponse], summary="Ask the knowledge base")
async def ask_question(request: QAAskRequest, db: Session = Depends(get_db)):
    try:
        result = qa_service.ask(db, request)
        return success(data=result, message="问答成功")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
