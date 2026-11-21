import base64
import dataclasses
import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.core.errors import EmptyReplyError, ModelNotFoundError, ModelUnavailableError
from app.domain.chat import ChatMessage, ModelInfo
from app.domain.personality import GenerationParams

logger = logging.getLogger(__name__)


class OllamaProvider:
    """LLMProvider implementation backed by the Ollama HTTP API."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        chat_timeout: httpx.Timeout | None = None,
        think: bool = False,
    ) -> None:
        self._client = client
        self._chat_timeout = chat_timeout or client.timeout
        # Reasoning models (qwen3.5, deepseek-r1...) otherwise "think" for tens of seconds before
        # the first visible word, and can spend the whole length budget without answering.
        self._think = think
        # Capabilities per model name, with the digest they were read for (/api/show is a
        # request per model; a re-pulled tag gets a new digest and is read again).
        self._capabilities: dict[str, tuple[str, frozenset[str]]] = {}

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
        models: list[ModelInfo] = []
        for raw in raw_models:
            info = _to_model_info(raw)
            capabilities = await self._capabilities_of(info.name, str(raw.get("digest", "")))
            models.append(dataclasses.replace(info, vision="vision" in capabilities))
        return models

    async def supports_vision(self, model: str) -> bool:
        return "vision" in await self._capabilities_of(model, digest=None)

    async def _capabilities_of(self, model: str, digest: str | None) -> frozenset[str]:
        """Ollama's capabilities for a model ("completion", "vision", "tools"...). Cached per
        name; `digest` (from /api/tags) invalidates a stale entry. Empty if unknown."""
        cached = self._capabilities.get(model)
        if cached and (digest is None or cached[0] == digest):
            return cached[1]
        try:
            response = await self._client.post("/api/show", json={"model": model})
            raw = response.json() if response.status_code == httpx.codes.OK else {}
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Ollama /api/show failed for a model: %s", type(exc).__name__)
            return frozenset()
        values = raw.get("capabilities") if isinstance(raw, dict) else None
        capabilities = (
            frozenset(str(c) for c in values) if isinstance(values, list) else frozenset()
        )
        if response.status_code == httpx.codes.OK:
            # Only models that exist get cached, so the cache stays as small as the model list.
            self._capabilities[model] = (digest or "", capabilities)
        return capabilities

    async def stream_chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        params: GenerationParams | None = None,
    ) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": [_ollama_message(m) for m in messages],
            "stream": True,
            "think": self._think,
        }
        options = _ollama_options(params)
        if options:
            payload["options"] = options
        produced = False
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
                        produced = True
                        yield content
                    if chunk.get("done"):
                        _check_finish(model, chunk.get("done_reason"), produced)
                        return
        except httpx.HTTPError as exc:
            raise _unavailable(exc) from exc


def _ollama_message(message: ChatMessage) -> dict[str, object]:
    out: dict[str, object] = {"role": message.role, "content": message.content}
    if message.images:
        # Ollama takes raw base64 (no data: prefix); it detects the format itself.
        out["images"] = [base64.b64encode(image.data).decode("ascii") for image in message.images]
    return out


def _ollama_options(params: GenerationParams | None) -> dict[str, float | int]:
    """Ollama takes sampling parameters under "options"; None keeps the model's default."""
    if params is None:
        return {}
    options = {"temperature": params.temperature, "top_p": params.top_p, "num_ctx": params.num_ctx}
    return {key: value for key, value in options.items() if value is not None}


def _check_finish(model: str, done_reason: object, produced: bool) -> None:
    if done_reason == "length":
        logger.warning("Ollama hit the length limit on %s (produced text: %s)", model, produced)
    if produced:
        return
    if done_reason == "length":
        raise EmptyReplyError(
            "El modelo agotó el límite de longitud sin llegar a responder. Prueba con un"
            " mensaje más corto o con el razonamiento desactivado (OLLAMA_THINK=false)."
        )
    raise EmptyReplyError


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
