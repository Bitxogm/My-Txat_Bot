from fastapi import Request

from app.ports.llm import LLMProvider


def get_llm_provider(request: Request) -> LLMProvider:
    provider: LLMProvider = request.app.state.llm_provider
    return provider
