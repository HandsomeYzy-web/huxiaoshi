from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from core.config import settings


class LLMService:
    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你是知识库问答助手。请严格依据提供的检索内容回答问题。"
                        "如果检索内容不足以支持结论，直接回答“根据当前知识库内容无法确定”。"
                        "回答要准确、简洁，并尽量综合多个知识库的信息。"
                    ),
                ),
                ("human", "问题：{question}\n\n检索内容：\n{context_block}"),
            ]
        )
        self.output_parser = StrOutputParser()

    def _create_model(self, streaming: bool = False):
        """创建 LLM 模型实例"""
        if (
            not settings.EFFECTIVE_LLM_BASE_URL
            or not settings.EFFECTIVE_LLM_API_KEY
            or not settings.EFFECTIVE_LLM_MODEL
        ):
            return None

        return ChatOpenAI(
            base_url=settings.EFFECTIVE_LLM_BASE_URL.rstrip("/"),
            api_key=settings.EFFECTIVE_LLM_API_KEY,
            model=settings.EFFECTIVE_LLM_MODEL,
            temperature=0.1,
            streaming=streaming,
        )

    def generate_answer(self, question: str, contexts: list[str]) -> tuple[str, str | None]:
        model = self._create_model(streaming=False)
        if model is None:
            snippet = "\n\n".join(contexts[:3])
            return (
                "未配置生成模型，当前返回检索到的高相关片段供前端展示。\n\n"
                f"{snippet}",
                None,
            )

        chain = self.prompt | model | self.output_parser
        context_block = "\n\n".join(
            f"[片段 {index + 1}]\n{context}" for index, context in enumerate(contexts)
        )
        answer = chain.invoke({"question": question, "context_block": context_block})
        return answer, settings.EFFECTIVE_LLM_MODEL

    def stream_answer(self, question: str, contexts: list[str]):
        """流式生成回答，生成器返回 (chunk: str, is_model_info: bool, model_name: str | None)"""
        model = self._create_model(streaming=True)

        # 未配置模型时，返回默认响应
        if model is None:
            snippet = "\n\n".join(contexts[:3])
            default_answer = (
                "未配置生成模型，当前返回检索到的高相关片段供前端展示。\n\n"
                f"{snippet}"
            )
            yield default_answer, False, None
            return

        # 首先返回模型信息标记
        yield "", True, settings.EFFECTIVE_LLM_MODEL

        # 构建上下文块
        context_block = "\n\n".join(
            f"[片段 {index + 1}]\n{context}" for index, context in enumerate(contexts)
        )

        # 创建流式链
        chain = self.prompt | model | self.output_parser

        # 流式生成
        for chunk in chain.stream({"question": question, "context_block": context_block}):
            if chunk:
                yield chunk, False, None


llm_service = LLMService()
