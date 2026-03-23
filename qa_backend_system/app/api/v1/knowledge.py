import os
import uuid
import shutil
from typing import List
from fastapi import APIRouter, UploadFile, File, Form, Depends, BackgroundTasks

from app.models.schemas import success_resp, error_resp, BaseResponse, KBCreateRequest, KBModelUpdateRequest
from app.core.logger import log

# 假设你有一个获取数据库 Session 的依赖函数 (后续需要用 SQLAlchemy 实现)
# from app.models.database import get_db
# from sqlalchemy.orm import Session

router = APIRouter()

# 基础上传目录配置
UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


### 1. 创建知识库
@router.post("/", response_model=BaseResponse)
async def create_knowledge_base(request: KBCreateRequest):
    """创建知识库，并校验模型是否可用"""
    # TODO: 1. 调用大模型 API 测试传入的 request.embedding_model 是否可用
    # 模拟校验失败
    if request.embedding_model not in ["text-embedding-v1", "text-embedding-v2", "m3e"]:
        return error_resp(400, "不支持或不可用的 Embedding 模型")

    kb_id = str(uuid.uuid4())
    # TODO: 2. 将 kb_id, name, description, embedding_model 存入 MySQL 的 knowledge_bases 表

    log.info(f"✅ 创建知识库成功: {request.name} ({kb_id})")
    return success_resp(data={"kb_id": kb_id})


### 2. 更改模型并触发异步重建
def background_rebuild_kb(kb_id: str, new_model: str):
    """后台运行的重建任务"""
    log.info(f"⏳ 开始重建知识库 {kb_id}，切换模型为: {new_model}")
    # TODO: 1. 更新 MySQL 中该 KB 的状态为 'rebuilding'
    # TODO: 2. 清空 Milvus 中该 kb_id 对应的所有旧向量数据
    # TODO: 3. 查出 MySQL 中该 KB 关联的所有 documents 的 file_path
    # TODO: 4. 重新读取文件 -> 重新向量化 -> 重新存入 Milvus
    # TODO: 5. 更新 MySQL 状态为 'active'
    log.info(f"✅ 知识库 {kb_id} 重建完成！")


@router.put("/{kb_id}/model", response_model=BaseResponse)
async def update_kb_model(kb_id: str, request: KBModelUpdateRequest, background_tasks: BackgroundTasks):
    """更改模型，立刻返回响应，后台慢慢重建"""
    # 将耗时的重建任务扔给后台
    background_tasks.add_task(background_rebuild_kb, kb_id, request.new_embedding_model)
    return success_resp(msg="模型已更改，后台正在重建知识库，请稍后查看。")


### 3. 多文件上传
@router.post("/{kb_id}/upload", response_model=BaseResponse)
async def upload_documents(
        kb_id: str,
        files: List[UploadFile] = File(...)
):
    """接收前端传来的多个文件，保存到本地并写入 MySQL"""
    saved_files = []

    # 为当前知识库创建专属文件夹
    kb_upload_dir = os.path.join(UPLOAD_DIR, kb_id)
    os.makedirs(kb_upload_dir, exist_ok=True)

    for file in files:
        file_ext = file.filename.split(".")[-1]
        doc_id = str(uuid.uuid4())
        # 为防止重名，物理文件使用 UUID 命名
        save_path = os.path.join(kb_upload_dir, f"{doc_id}.{file_ext}")

        # 将文件写入磁盘
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # TODO: 将文件信息 (doc_id, kb_id, 原始文件名, 文件类型, 物理路径) 插入 MySQL 的 documents 表

        saved_files.append({"doc_id": doc_id, "file_name": file.filename})
        log.info(f"📁 文件上传成功: {file.filename} -> {save_path}")

    return success_resp(data={"uploaded_files": saved_files})


### 4. 切分预览接口 (核心难点)
@router.post("/preview-chunk", response_model=BaseResponse)
async def preview_document_chunk(
        file: UploadFile = File(...),
        chunk_size: int = Form(500),
        chunk_overlap: int = Form(50)
):
    """接收单个文件和切分规则，返回前 N 个切分片段，不入库"""
    from langchain_community.document_loaders import UnstructuredFileLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    # 1. 临时保存文件用于预览
    temp_path = os.path.join(UPLOAD_DIR, f"temp_{file.filename}")
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # 2. 动态检测并加载文件内容 (这里以最基础的 Unstructured 为例)
        loader = UnstructuredFileLoader(temp_path)
        docs = loader.load()

        # 3. 应用前端传来的切分规则
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        split_docs = text_splitter.split_documents(docs)

        # 4. 只取前 3 个片段给前端展示
        preview_chunks = [doc.page_content for doc in split_docs[:3]]

        return success_resp(data={
            "total_chunks": len(split_docs),
            "preview_chunks": preview_chunks
        })
    except Exception as e:
        log.error(f"预览切分失败: {str(e)}")
        return error_resp(500, f"文件解析失败: {str(e)}")
    finally:
        # 5. 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)


### 5. 正式处理并入库 (异步)
def background_process_document(doc_id: str):
    """后台执行真正的：解析 -> 切分 -> 向量化 -> Milvus入库"""
    log.info(f"⏳ 开始处理文档 {doc_id} 的向量化入库流程...")
    # TODO: 1. 更新 MySQL 中该文档状态为 'processing'
    # TODO: 2. 从 MySQL 读取文件路径和专属切分规则
    # TODO: 3. 使用 LangChain Loader 加载文件
    # TODO: 4. 使用 LangChain Splitter 切分文本
    # TODO: 5. 获取 KB 绑定的 Embedding 模型，调用 API 计算向量
    # TODO: 6. 存入 Milvus (附加 kb_id 和 doc_id 作为 metadata)
    # TODO: 7. 更新 MySQL 中该文档状态为 'success'，并记录生成的 chunk_count
    log.info(f"✅ 文档 {doc_id} 向量化入库成功！")


@router.post("/{doc_id}/process", response_model=BaseResponse)
async def process_document(doc_id: str, background_tasks: BackgroundTasks):
    """触发文档处理工作流"""
    # 放入后台任务列队，立刻给前端返回 200，让前端通过轮询或 WebSocket 查看状态
    background_tasks.add_task(background_process_document, doc_id)
    return success_resp(msg="文档已加入处理队列，正在后台向量化。")