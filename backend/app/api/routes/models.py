from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_app_settings, get_llm_provider
from app.core.config import Settings
from app.ports.llm import LLMProvider

router = APIRouter(tags=["models"])


class ModelOut(BaseModel):
    name: str
    size_bytes: int
    family: str | None
    parameter_size: str | None
    quantization: str | None
    remote: bool
    vision: bool


class ModelsResponse(BaseModel):
    models: list[ModelOut]
    default_model: str | None


@router.get("/models")
async def list_models(
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ModelsResponse:
    models = await llm.list_models()
    return ModelsResponse(
        models=[
            ModelOut(
                name=m.name,
                size_bytes=m.size_bytes,
                family=m.family,
                parameter_size=m.parameter_size,
                quantization=m.quantization,
                remote=m.remote,
                vision=m.vision,
            )
            for m in models
        ],
        default_model=settings.default_model or None,
    )
