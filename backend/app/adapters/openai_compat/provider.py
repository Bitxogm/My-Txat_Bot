"""LLMProvider for OpenAI-compatible chat APIs (Groq, OpenRouter, Cerebras...).

Only `GET /models` and streaming `POST /chat/completions` are used, so any provider that
implements that subset works by changing CLOUD_BASE_URL.
"""

import base64
import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.core.errors import (
    ContextTooLongError,
    EmptyReplyError,
    ModelNotFoundError,
    ModelRateLimitedError,
    ModelUnavailableError,
)
from app.domain.chat import ChatMessage, ModelInfo
from app.domain.personality import GenerationParams

logger = logging.getLogger(__name__)

# Groq and others list speech, moderation and embedding models next to chat ones.
_NON_CHAT_MARKERS = ("whisper", "tts", "guard", "embed", "moderation", "playai", "orpheus")


class OpenAICompatibleProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        name: str,
        allowed_models: Sequence[str] = (),
        chat_timeout: httpx.Timeout | None = None,
        vision_models: Sequence[str] = (),
        local: bool = False,
        key_variable: str = "",
    ) -> None:
        self._client = client
        self.name = name
        self._allowed = set(allowed_models)
        self._vision = set(vision_models)
        # A server on this machine (LM Studio, llama.cpp): its models count as local.
        self._local = local
        self._key_variable = key_variable or f"PROVIDER_{name.upper()}_API_KEY"
        self._chat_timeout = chat_timeout or client.timeout

    async def is_available(self) -> bool:
        try:
            response = await self._client.get("/models")
        except httpx.HTTPError as exc:
            logger.warning("%s unreachable: %s", self.name, type(exc).__name__)
            return False
        return response.status_code == httpx.codes.OK

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self._client.get("/models")
        except httpx.HTTPError as exc:
            raise self._unavailable(exc) from exc
        self._raise_for_status(response, model=None)
        try:
            raw = response.json().get("data", [])
        except ValueError as exc:
            raise ModelUnavailableError("Respuesta no válida del proveedor en la nube") from exc
        ids = sorted(str(m.get("id", "")) for m in raw if isinstance(m, dict) and m.get("id"))
        if self._allowed:
            ids = [i for i in ids if i in self._allowed]
        else:
            ids = [i for i in ids if not any(marker in i.lower() for marker in _NON_CHAT_MARKERS)]
        return [
            ModelInfo(
                name=i,
                size_bytes=0,
                remote=not self._local,
                vision=i in self._vision,
                provider=self.name,
            )
            for i in ids
        ]

    async def supports_vision(self, model: str) -> bool:
        return model in self._vision and self._is_allowed(model)

    def _is_allowed(self, model: str) -> bool:
        return not self._allowed or model in self._allowed

    async def stream_chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        params: GenerationParams | None = None,
    ) -> AsyncIterator[str]:
        if not self._is_allowed(model):
            # CLOUD_MODELS is an allowlist, also for clients that ask for a model by name.
            raise ModelNotFoundError(f"El modelo '{model}' no está permitido en {self.name}")
        payload: dict[str, object] = {
            "model": model,
            "messages": [_openai_message(m) for m in messages],
            "stream": True,
        }
        # temperature and top_p are top-level here; num_ctx has no equivalent in this API (the
        # provider fixes the context window), so it is dropped on purpose.
        if params is not None:
            if params.temperature is not None:
                payload["temperature"] = params.temperature
            if params.top_p is not None:
                payload["top_p"] = params.top_p
        produced = False
        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=payload, timeout=self._chat_timeout
            ) as response:
                if response.status_code != httpx.codes.OK:
                    await response.aread()
                    self._raise_for_status(response, model=model)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    chunk = _parse(data)
                    if "error" in chunk:
                        logger.warning("%s stream error: %s", self.name, _error_text(chunk))
                        raise ModelUnavailableError("El modelo en la nube falló al responder")
                    choice = (chunk.get("choices") or [{}])[0]
                    content = (choice.get("delta") or {}).get("content") or ""
                    if content:
                        produced = True
                        yield content
                    if choice.get("finish_reason") == "length" and not produced:
                        raise EmptyReplyError(
                            "El modelo agotó el límite de longitud sin llegar a responder."
                        )
        except httpx.HTTPError as exc:
            raise self._unavailable(exc) from exc
        if not produced:
            raise EmptyReplyError

    def _raise_for_status(self, response: httpx.Response, model: str | None) -> None:
        status = response.status_code
        if status == httpx.codes.OK:
            return
        # Never log request headers: they carry the API key.
        logger.warning("%s answered %d: %.300s", self.name, status, response.text)
        if status in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            raise ModelUnavailableError(
                f"{self.name} rechazó la clave de API (revisa {self._key_variable})"
            )
        if status in (httpx.codes.BAD_REQUEST, httpx.codes.REQUEST_ENTITY_TOO_LARGE) and (
            "context_length" in response.text or "context window" in response.text.lower()
        ):
            raise ContextTooLongError
        if status == httpx.codes.NOT_FOUND and model:
            raise ModelNotFoundError(f"El modelo '{model}' no existe en {self.name}")
        if status == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = response.headers.get("retry-after")
            headers = {"Retry-After": retry_after} if retry_after else None
            raise ModelRateLimitedError(headers=headers)
        raise ModelUnavailableError(f"{self.name} no está disponible ahora mismo")

    def _unavailable(self, exc: httpx.HTTPError) -> ModelUnavailableError:
        logger.warning("%s request failed: %s", self.name, type(exc).__name__)
        if isinstance(exc, httpx.TimeoutException):
            return ModelUnavailableError(f"{self.name} tardó demasiado en responder")
        return ModelUnavailableError(f"No se puede conectar con {self.name}")


def _openai_message(message: ChatMessage) -> dict[str, object]:
    if not message.images:
        return {"role": message.role, "content": message.content}
    parts: list[dict[str, object]] = [{"type": "text", "text": message.content}]
    for image in message.images:
        encoded = base64.b64encode(image.data).decode("ascii")
        parts.append(
            {"type": "image_url", "image_url": {"url": f"data:{image.mime};base64,{encoded}"}}
        )
    return {"role": message.role, "content": parts}


def build_openai_compatible_client(
    base_url: str, api_key: str, timeout_seconds: float
) -> httpx.AsyncClient:
    """Without a key (LM Studio, llama.cpp) no Authorization header is sent at all."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_seconds
    )


def _parse(data: str) -> dict[str, Any]:
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ModelUnavailableError("Respuesta no válida del proveedor en la nube") from exc
    if not isinstance(parsed, dict):
        raise ModelUnavailableError("Respuesta no válida del proveedor en la nube")
    return parsed


def _error_text(chunk: dict[str, Any]) -> str:
    error = chunk.get("error")
    if isinstance(error, dict):
        return str(error.get("message", ""))[:300]
    return str(error)[:300]
