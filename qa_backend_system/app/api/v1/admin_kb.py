# app/api/v1/admin_kb.py
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import os
import shutil
from typing import List
from fastapi import UploadFile, File, BackgroundTasks

from app.models.entities import Document
from app.core.milvus_client import get_vector_store
from app.models.database import get_db
from app.models.entities import KnowledgeBase
from app.models.schemas import BaseResponse, KBCreateRequest, success_resp, error_resp
from app.core.logger import log

router = APIRouter()

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

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

@router.post("/{kb_id}/upload", response_model=BaseResponse)
async def upload_documents(
        kb_id: str,
        files: List[UploadFile] = File(...),  # 🌟 核心改变：接收文件列表
        db: Session = Depends(get_db)
):
    """批量上传多个文件，保存物理文件并写入 MySQL records"""
    saved_docs = []
    kb_upload_dir = os.path.join(UPLOAD_DIR, kb_id)
    os.makedirs(kb_upload_dir, exist_ok=True)

    for file in files:
        file_ext = file.filename.split(".")[-1].lower()
        if file_ext not in ["doc", "docx"]:
            # 如果发现格式不对，直接阻断并提示
            return error_resp(400, f"文件 [{file.filename}] 格式不支持，目前仅支持 .doc, .docx")

        doc_id = str(uuid.uuid4())
        save_path = os.path.join(kb_upload_dir, f"{doc_id}.{file_ext}")

        try:
            # 将文件流写入磁盘
            with open(save_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # 准备写入 MySQL 的对象
            new_doc = Document(
                id=doc_id,
                kb_id=kb_id,
                file_name=file.filename,
                file_type=file_ext,
                file_path=save_path,
                chunk_rule={"chunk_size": 500, "chunk_overlap": 50},
                status="pending"
            )
            db.add(new_doc)
            saved_docs.append({"doc_id": doc_id, "file_name": file.filename})
            log.info(f"📁 文件准备就绪: {file.filename}")

        except Exception as e:
            db.rollback()
            log.error(f"❌ 文件保存失败: {str(e)}")
            return error_resp(500, f"文件 {file.filename} 保存失败")

    # 所有文件都成功写入磁盘后，再一次性提交数据库事务
    db.commit()
    return success_resp(data={"uploaded_files": saved_docs})


def background_process_word(doc_id: str, db: Session):
    """后台任务：使用 UnstructuredWordDocumentLoader 解析 Word"""
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc: return

        log.info(f"⏳ 开始处理 Word 文档 [{doc.file_name}]...")
        doc.status = 'processing'
        db.commit()

        # 1. 专门针对 Word 的加载器
        from langchain_community.document_loaders import UnstructuredWordDocumentLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        loader = UnstructuredWordDocumentLoader(doc.file_path)
        raw_docs = loader.load()

        # 2. 文本切分策略
        chunk_rule = doc.chunk_rule or {"chunk_size": 500, "chunk_overlap": 50}
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_rule.get("chunk_size", 500),
            chunk_overlap=chunk_rule.get("chunk_overlap", 50)
        )
        split_docs = text_splitter.split_documents(raw_docs)

        # 3. 植入核心元数据 (过滤检索全靠它)
        for chunk in split_docs:
            # 拿出现有的 source（如果没有，就用文件的绝对路径兜底）
            source_val = chunk.metadata.get("source", doc.file_path)

            # 暴力重置 metadata，只保留我们系统真正需要的 4 个核心字段！
            # 这样无论什么格式的文档，入库的 Schema 永远是统一的。
            chunk.metadata = {
                "kb_id": str(doc.kb_id),
                "doc_id": str(doc.id),
                "file_name": str(doc.file_name),
                "source": str(source_val)  # 满足 LangChain 默认的强迫症
            }

        # 4. 获取带有 E5 模型的 Milvus 实例并入库
        log.info("① 准备获取 vector_store")
        vector_store = get_vector_store()

        log.info("② vector_store 获取成功，准备 add_documents")
        vector_store.add_documents(documents=split_docs)

        log.info("③ add_documents 完成")

        # 5. 更新 MySQL 状态
        doc.status = 'success'
        doc.chunk_count = len(split_docs)
        # TODO: 下一阶段在这里调用 LLM 生成 doc.summary 作为一级索引
        db.commit()
        log.info(f"✅ Word 文档 [{doc.file_name}] 切分为 {len(split_docs)} 块，成功入库 Milvus！")

    except Exception as e:
        log.error(f"❌ Word 文档处理失败: {str(e)}", exc_info=True)
        doc.status = 'failed'
        doc.error_msg = str(e)
        db.commit()
    finally:
        db.close()

@router.post("/{doc_id}/process", response_model=BaseResponse)
async def process_document(doc_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """触发向量化任务"""
    # 不能直接传被 Depends 注入的 db 给后台任务，会话会提前关闭，需要新建个独立 session 或在后台方法内新建
    from app.models.database import SessionLocal
    bg_db = SessionLocal()
    background_tasks.add_task(background_process_word, doc_id, bg_db)
    return success_resp(msg="文档已加入处理队列，后台正在切分并计算向量。")