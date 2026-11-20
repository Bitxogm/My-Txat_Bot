import logging

import httpx

logger = logging.getLogger(__name__)


class OllamaProvider:
    """LLMProvider implementation backed by the Ollama HTTP API."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

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


def build_ollama_client(base_url: str, timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)
