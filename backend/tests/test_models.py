import httpx

from app.core.errors import ModelUnavailableError
from app.domain.chat import ModelInfo
from tests.conftest import FakeLLMProvider


async def test_lists_models(client: httpx.AsyncClient, fake_llm: FakeLLMProvider) -> None:
    fake_llm.models = [
        ModelInfo(
            name="qwen2.5:7b",
            size_bytes=4_700_000_000,
            family="qwen2",
            parameter_size="7.6B",
            quantization="Q4_K_M",
        )
    ]

    response = await client.get("/api/models")

    assert response.status_code == 200
    assert response.json() == {
        "models": [
            {
                "name": "qwen2.5:7b",
                "size_bytes": 4_700_000_000,
                "family": "qwen2",
                "parameter_size": "7.6B",
                "quantization": "Q4_K_M",
                "remote": False,
                "vision": False,
            }
        ],
        "default_model": None,
    }


async def test_models_when_ollama_down(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.fail_before = ModelUnavailableError()

    response = await client.get("/api/models")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_UNAVAILABLE"
