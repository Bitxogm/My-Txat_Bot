import httpx

from tests.conftest import FakeLLMProvider


async def test_health_reports_ollama_up(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ollama": "up"}


async def test_health_stays_200_when_ollama_down(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.available = False

    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ollama": "down"}
