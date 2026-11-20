import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.core.errors import ModelNotFoundError, ModelUnavailableError
from app.domain.chat import ChatMessage, ModelInfo

logger = logging.getLogger(__name__)


class OllamaProvider:
    """LLMProvider implementation backed by the Ollama HTTP API."""

    def __init__(
        self, client: httpx.AsyncClient, chat_timeout: httpx.Timeout | None = None
    ) -> None:
        self._client = client
        self._chat_timeout = chat_timeout or client.timeout

    async def is_available(self) -> bool:
        try:
            response = await self._client.get("/api/version")
        except httpx.HTTPError as exc:
            logger.warning("Ollama unreachable: %s", type(exc).__name__)
            return False
        if response.status_code != httpx.codes.OK:
            logger.warning("Ollama answered %d on /api/version", response.status_code)
            return False
        return True

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self._client.get("/api/tags")
        except httpx.HTTPError as exc:
            raise _unavailable(exc) from exc
        if response.status_code != httpx.codes.OK:
            logger.warning("Ollama answered %d on /api/tags", response.status_code)
            raise ModelUnavailableError
        try:
            raw_models = response.json().get("models", [])
        except ValueError as exc:
            raise ModelUnavailableError("Respuesta no válida del servidor de modelos") from exc
        return [_to_model_info(raw) for raw in raw_models]

    async def stream_chat(self, model: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        try:
            async with self._client.stream(
                "POST", "/api/chat", json=payload, timeout=self._chat_timeout
            ) as response:
                if response.status_code == httpx.codes.NOT_FOUND:
                    raise ModelNotFoundError(f"El modelo '{model}' no existe en Ollama")
                if response.status_code != httpx.codes.OK:
                    await response.aread()
                    logger.warning(
                        "Ollama answered %d on /api/chat: %s", response.status_code, response.text
                    )
                    raise ModelUnavailableError
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = _parse_line(line)
                    if "error" in chunk:
                        logger.warning("Ollama stream error: %s", chunk["error"])
                        raise ModelUnavailableError("El modelo falló al generar la respuesta")
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        return
        except httpx.HTTPError as exc:
            raise _unavailable(exc) from exc


def build_ollama_client(base_url: str, timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)


def build_chat_timeout(connect_seconds: float, read_seconds: float) -> httpx.Timeout:
    # Read timeout is the max gap between chunks; loading a model on the GPU can take a while.
    return httpx.Timeout(connect_seconds, read=read_seconds)


def _unavailable(exc: httpx.HTTPError) -> ModelUnavailableError:
    logger.warning("Ollama request failed: %s", type(exc).__name__)
    if isinstance(exc, httpx.TimeoutException):
        return ModelUnavailableError("El servidor de modelos tardó demasiado en responder")
    return ModelUnavailableError()


def _parse_line(line: str) -> dict[str, Any]:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON line from Ollama: %.200s", line)
        raise ModelUnavailableError("Respuesta no válida del servidor de modelos") from exc
    if not isinstance(parsed, dict):
        raise ModelUnavailableError("Respuesta no válida del servidor de modelos")
    return parsed


def _to_model_info(raw: dict[str, Any]) -> ModelInfo:
    details = raw.get("details") or {}
    return ModelInfo(
        name=str(raw.get("name") or raw.get("model", "")),
        size_bytes=int(raw.get("size", 0)),
        family=details.get("family"),
        parameter_size=details.get("parameter_size"),
        quantization=details.get("quantization_level"),
    )
