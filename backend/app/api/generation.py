"""Generation settings shared by the chat routes."""

import dataclasses

from app.core.config import Settings
from app.domain.personality import GenerationParams


def context_for(
    model: str, params: GenerationParams, settings: Settings
) -> tuple[int, GenerationParams]:
    """Token budget to fit the history into, and the parameters to send.

    Ollama models get `OLLAMA_NUM_CTX` unless the personality sets its own `num_ctx`: Ollama's
    default (4096) is too small for images and long answers. Models of an OpenAI-compatible
    provider use its `PROVIDER_<NAME>_CONTEXT_TOKENS` (their window is set by the server, so
    num_ctx is not sent).
    """
    provider = settings.provider_for(model)
    if provider is not None:
        return provider.context_tokens, params
    num_ctx = params.num_ctx or settings.ollama_num_ctx
    return num_ctx, dataclasses.replace(params, num_ctx=num_ctx)
