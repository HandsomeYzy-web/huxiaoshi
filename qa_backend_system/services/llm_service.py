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

    def generate_answer(self, question: str, contexts: list[str]) -> tuple[str, str | None]:
        if (
            not settings.EFFECTIVE_LLM_BASE_URL
            or not settings.EFFECTIVE_LLM_API_KEY
            or not settings.EFFECTIVE_LLM_MODEL
        ):
            snippet = "\n\n".join(contexts[:3])
            return (
                "未配置生成模型，当前返回检索到的高相关片段供前端展示。\n\n"
                f"{snippet}",
                None,
            )

        model = ChatOpenAI(
            base_url=settings.EFFECTIVE_LLM_BASE_URL.rstrip("/"),
            api_key=settings.EFFECTIVE_LLM_API_KEY,
            model=settings.EFFECTIVE_LLM_MODEL,
            temperature=0.1,
        )
        chain = self.prompt | model | self.output_parser
        context_block = "\n\n".join(
            f"[片段 {index + 1}]\n{context}" for index, context in enumerate(contexts)
        )
        answer = chain.invoke({"question": question, "context_block": context_block})
        return answer, settings.EFFECTIVE_LLM_MODEL


llm_service = LLMService()
