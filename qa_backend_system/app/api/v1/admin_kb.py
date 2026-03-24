# app/api/v1/admin_kb.py
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.entities import KnowledgeBase
from app.models.schemas import BaseResponse, KBCreateRequest, success_resp, error_resp
from app.core.logger import log

router = APIRouter()


@router.post("/", response_model=BaseResponse)
async def create_knowledge_base(request: KBCreateRequest, db: Session = Depends(get_db)):
    """
    接口 1：创建新的知识库
    """
    try:
        kb_id = str(uuid.uuid4())

        # 1. 组装数据库实体
        new_kb = KnowledgeBase(
            id=kb_id,
            name=request.name,
            description=request.description,
            embedding_model=request.embedding_model,
            status="active"
        )

        # 2. 存入 MySQL
        db.add(new_kb)
        db.commit()

        log.info(f"✅ 知识库创建成功: {request.name} ({kb_id})")
        return success_resp(data={"kb_id": kb_id})
    except Exception as e:
        db.rollback()
        log.error(f"❌ 知识库创建失败: {str(e)}")
        return error_resp(500, "数据库写入失败，请检查服务状态")


@router.get("/list", response_model=BaseResponse)
async def list_knowledge_bases(db: Session = Depends(get_db)):
    """
    接口 2：获取所有知识库列表
    """
    try:
        # 按创建时间倒序查询所有状态为 active 的知识库
        kbs = db.query(KnowledgeBase).filter(
            KnowledgeBase.status == 'active'
        ).order_by(KnowledgeBase.created_at.desc()).all()

        # 格式化返回给前端的数据
        result = []
        for kb in kbs:
            result.append({
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "embedding_model": kb.embedding_model,
                # 格式化时间为漂亮的字符串
                "created_at": kb.created_at.strftime("%Y-%m-%d %H:%M:%S") if kb.created_at else ""
            })

        return success_resp(data=result)
    except Exception as e:
        log.error(f"❌ 获取知识库列表失败: {str(e)}")
        return error_resp(500, "查询数据库失败")