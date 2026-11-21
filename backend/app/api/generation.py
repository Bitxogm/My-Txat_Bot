"""Generation settings shared by the chat routes."""

import dataclasses

from app.core.config import Settings
from app.domain.personality import GenerationParams


def context_for(
    model: str, params: GenerationParams, settings: Settings
) -> tuple[int, GenerationParams]:
    """Token budget to fit the history into, and the parameters to send.

    Local models get `OLLAMA_NUM_CTX` unless the personality sets its own `num_ctx`: Ollama's
    default (4096) is too small for images and long answers. Cloud models have a window fixed by
    the provider; `CLOUD_CONTEXT_TOKENS` is the budget assumed for them.
    """
    if settings.cloud_enabled and model.startswith(f"{settings.cloud_name}/"):
        return settings.cloud_context_tokens, params
    num_ctx = params.num_ctx or settings.ollama_num_ctx
    return num_ctx, dataclasses.replace(params, num_ctx=num_ctx)
