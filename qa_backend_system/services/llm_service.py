import requests

from core.config import settings


class LLMService:
    def generate_answer(self, question: str, contexts: list[str]) -> tuple[str, str | None]:
        if not settings.LLM_BASE_URL or not settings.LLM_API_KEY or not settings.LLM_MODEL:
            snippet = "\n\n".join(contexts[:3])
            return (
                "未配置生成模型，当前返回检索到的高相关片段供前端展示。\n\n"
                f"{snippet}",
                None,
            )

        api_url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
        system_prompt = (
            "你是知识库问答助手。请严格基于提供的上下文回答问题。"
            "如果上下文不足以支持结论，直接回答“根据当前知识库内容无法确定”。"
        )
        user_prompt = (
            f"问题：{question}\n\n"
            "上下文：\n"
            + "\n\n".join(f"[片段 {index + 1}]\n{context}" for index, context in enumerate(contexts))
        )
        response = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"], settings.LLM_MODEL


llm_service = LLMService()
