import os
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from ...models.schemas import ChatRequest
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

router = APIRouter()

# 初始化通义千问 LLM (使用 OpenAI 兼容模式)
llm = ChatTongyi(
    model=os.getenv("DASHSCOPE_MODEL_NAME"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    streaming=True
)

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个专业、友好的企业级智能问答助手。"),
    ("human", "{question}")
])

chain = prompt | llm

# 定义一个异步生成器，用于逐字返回大模型的回答
async def generate_chat_stream(query: str):
    # astream 是 LangChain 提供的异步流式输出方法
    async for chunk in chain.astream({"question": query}):
        if chunk.content:
            # yield 将每次生成的一小块文本推给前端
            yield chunk.content

@router.post("/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    流式问答接口
    """
    return StreamingResponse(
        generate_chat_stream(request.query),
        media_type="text/event-stream"
    )