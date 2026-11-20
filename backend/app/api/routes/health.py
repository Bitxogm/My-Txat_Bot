from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_llm_provider
from app.ports.llm import LLMProvider

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    ollama: Literal["up", "down"]


@router.get("/health")
async def health(
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> HealthResponse:
    # Ollama being down must not mark the container unhealthy: it runs on another machine.
    return HealthResponse(status="ok", ollama="up" if await llm.is_available() else "down")
