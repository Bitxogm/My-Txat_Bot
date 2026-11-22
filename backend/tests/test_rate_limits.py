import httpx
import pytest

from app.adapters.openai_compat.provider import OpenAICompatibleProvider, retry_after
from app.core.errors import ModelRateLimitedError
from app.domain.chat import ChatMessage
from tests.conftest import FakeLLMProvider
from tests.image_fixtures import png

# --- how long to wait --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "seconds"),
    [
        ({"retry-after": "7"}, 7),
        ({"retry-after": "7.2"}, 8),  # rounded up
        ({"retry-after": "99999"}, 3600),  # capped
        (  # Groq without Retry-After: the exhausted bucket decides
            {
                "x-ratelimit-remaining-tokens": "0",
                "x-ratelimit-reset-tokens": "7.66s",
                "x-ratelimit-remaining-requests": "12",
                "x-ratelimit-reset-requests": "2m59.56s",
            },
            8,
        ),
        (  # neither reported as exhausted: the longer one
            {"x-ratelimit-reset-tokens": "1.5s", "x-ratelimit-reset-requests": "1m2s"},
            62,
        ),
        ({"x-ratelimit-reset-tokens": "250ms"}, 1),
        ({"x-ratelimit-reset-tokens": "pronto"}, None),
        ({}, None),
    ],
)
def test_retry_after(headers: dict[str, str], seconds: int | None) -> None:
    assert retry_after(httpx.Headers(headers)) == seconds


async def test_provider_429_names_the_provider_and_the_wait() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(429, headers={"x-ratelimit-reset-tokens": "12s"})
        ),
        base_url="http://c.test/v1",
    )
    provider = OpenAICompatibleProvider(client, "groq")

    with pytest.raises(ModelRateLimitedError) as caught:
        [c async for c in provider.stream_chat("m", [ChatMessage(role="user", content="x")])]

    assert caught.value.details == {"provider": "groq", "retry_after": 12}
    assert caught.value.headers == {"Retry-After": "12"}
    assert "disponible en 12 s" in caught.value.message


# --- the chat -------------------------------------------------------------------------------


async def new_conversation(client: httpx.AsyncClient) -> str:
    return str((await client.post("/api/conversations", json={"model": "m"})).json()["id"])


@pytest.mark.parametrize(
    ("wait", "message"),
    [(12, "disponible en 12 s"), (None, "Espera un poco")],
)
async def test_429_body_tells_the_client_when_and_who(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider, wait: int | None, message: str
) -> None:
    conversation_id = await new_conversation(client)
    fake_llm.fail_before = ModelRateLimitedError.for_provider("groq", wait)

    response = await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": "hola"}
    )

    assert response.status_code == 429
    error = response.json()["error"]
    assert (error["code"], error["provider"], error["retry_after"]) == (
        "MODEL_RATE_LIMITED",
        "groq",
        wait,
    )
    assert message in error["message"] and error["request_id"]
    assert (response.headers.get("retry-after") is not None) == (wait is not None)


async def test_429_undoes_the_turn_and_frees_the_files(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.vision_models.add("m")
    conversation_id = await new_conversation(client)
    upload = await client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={"file": ("a.png", png(), "image/png")},
    )
    attachment_id = upload.json()["id"]
    fake_llm.fail_before = ModelRateLimitedError.for_provider("groq", 5)

    response = await client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "mira", "attachment_ids": [attachment_id]},
    )

    assert response.status_code == 429
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"] == []
    pending = (await client.get(f"/api/conversations/{conversation_id}/attachments")).json()
    assert [(a["id"], a["sent"]) for a in pending["attachments"]] == [(attachment_id, False)]

    # Sending again (e.g. with the local model) works and takes the same file.
    fake_llm.fail_before = None
    again = await client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "mira", "attachment_ids": [attachment_id]},
    )
    assert again.status_code == 200
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["content"] for m in detail["messages"] if m["role"] == "user"] == ["mira"]


async def test_a_429_mid_stream_carries_the_same_fields(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await new_conversation(client)
    fake_llm.fail_after = ModelRateLimitedError.for_provider("groq", 30)

    response = await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": "hola"}
    )

    assert '"provider": "groq"' in response.text and '"retry_after": 30' in response.text
