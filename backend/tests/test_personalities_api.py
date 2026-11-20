import json

import httpx
import pytest

from app.domain.builtin_personalities import BUILTIN_PERSONALITIES
from app.domain.personality import DEFAULT_PERSONALITY_ID
from app.domain.prompts import BASE_PROMPT, PERSONALITY_HEADER
from tests.conftest import FakeLLMProvider

NEW = {
    "name": "Mi pentester",
    "icon": "crosshair",
    "description": "Para mis labs",
    "system_prompt": "Responde en una línea.",
    "temperature": 0.1,
    "top_p": 0.8,
    "num_ctx": 4096,
}


def code(response: httpx.Response) -> str:
    return str(response.json()["error"]["code"])


async def create(client: httpx.AsyncClient, **overrides: object) -> dict[str, object]:
    response = await client.post("/api/personalities", json={**NEW, **overrides})
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_requires_a_session(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.get("/api/personalities")).status_code == 401


async def test_lists_the_eight_builtins_first(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/personalities")).json()

    ids = [p["id"] for p in body["personalities"]]
    assert ids == list(BUILTIN_PERSONALITIES)
    auditor = body["personalities"][-1]
    assert auditor["name"] == "Auditor de Huella Digital"
    assert (auditor["icon"], auditor["temperature"], auditor["top_p"], auditor["num_ctx"]) == (
        "user-search",
        0.3,
        0.9,
        8192,
    )


async def test_create_edit_and_delete_a_copy(client: httpx.AsyncClient) -> None:
    created = await create(client)
    assert created["builtin"] is False

    patched = await client.patch(
        f"/api/personalities/{created['id']}", json={"name": "Renombrada", "num_ctx": None}
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renombrada"
    assert patched.json()["num_ctx"] is None
    assert patched.json()["temperature"] == 0.1  # untouched fields keep their value

    assert (await client.delete(f"/api/personalities/{created['id']}")).status_code == 204
    missing = await client.get(f"/api/personalities/{created['id']}")
    assert code(missing) == "PERSONALITY_NOT_FOUND"


@pytest.mark.parametrize("builtin_id", list(BUILTIN_PERSONALITIES))
async def test_builtins_cannot_be_edited_or_deleted(
    client: httpx.AsyncClient, builtin_id: str
) -> None:
    patch = await client.patch(f"/api/personalities/{builtin_id}", json={"name": "x"})
    delete = await client.delete(f"/api/personalities/{builtin_id}")

    assert patch.status_code == delete.status_code == 403
    assert code(patch) == code(delete) == "PERSONALITY_BUILTIN"
    assert set(patch.json()["error"]) == {"code", "message", "request_id"}
    still = (await client.get(f"/api/personalities/{builtin_id}")).json()
    assert still["name"] == BUILTIN_PERSONALITIES[builtin_id].name


@pytest.mark.parametrize(
    "payload",
    [
        {**NEW, "builtin": True},
        {**NEW, "id": "builtin-mentor-ctf"},
        {**NEW, "created_at": "2020-01-01T00:00:00Z"},
    ],
)
async def test_clients_cannot_create_builtins_or_choose_ids(
    client: httpx.AsyncClient, payload: dict[str, object]
) -> None:
    response = await client.post("/api/personalities", json=payload)

    assert response.status_code == 422


async def test_patch_cannot_flag_a_copy_as_builtin(client: httpx.AsyncClient) -> None:
    created = await create(client)

    response = await client.patch(f"/api/personalities/{created['id']}", json={"builtin": True})

    assert response.status_code == 422
    assert (await client.get(f"/api/personalities/{created['id']}")).json()["builtin"] is False


async def test_duplicate_a_builtin_gives_an_editable_copy(client: httpx.AsyncClient) -> None:
    response = await client.post(f"/api/personalities/{DEFAULT_PERSONALITY_ID}/duplicate")

    assert response.status_code == 201
    copy = response.json()
    assert copy["name"] == "Mentor CTF (copia)"
    assert copy["builtin"] is False
    assert copy["id"] != DEFAULT_PERSONALITY_ID
    assert copy["system_prompt"] == BUILTIN_PERSONALITIES[DEFAULT_PERSONALITY_ID].system_prompt
    edited = await client.patch(f"/api/personalities/{copy['id']}", json={"temperature": 1.2})
    assert edited.status_code == 200


async def test_duplicate_name_is_trimmed_to_fit(client: httpx.AsyncClient) -> None:
    created = await create(client, name="x" * 60)

    copy = (await client.post(f"/api/personalities/{created['id']}/duplicate")).json()

    assert len(copy["name"]) == 60
    assert copy["name"].endswith(" (copia)")


@pytest.mark.parametrize(
    "overrides",
    [
        {"temperature": 2.1},
        {"temperature": -0.1},
        {"top_p": 0},
        {"top_p": 1.1},
        {"num_ctx": 100},
        {"num_ctx": 16385},
        {"name": "   "},
        {"name": "x" * 61},
        {"system_prompt": ""},
        {"system_prompt": "x" * 8001},
        {"icon": "<script>"},
        {"description": "x" * 201},
    ],
)
async def test_validates_ranges(client: httpx.AsyncClient, overrides: dict[str, object]) -> None:
    response = await client.post("/api/personalities", json={**NEW, **overrides})

    assert response.status_code == 422


@pytest.mark.parametrize("bad_id", ["../x", "builtin-", "BUILTIN-X", "0" * 31])
async def test_rejects_malformed_ids(client: httpx.AsyncClient, bad_id: str) -> None:
    assert (await client.get(f"/api/personalities/{bad_id}")).status_code in {404, 422}


async def test_unknown_id_is_404_before_403(client: httpx.AsyncClient) -> None:
    response = await client.delete("/api/personalities/builtin-no-existe")

    assert code(response) == "PERSONALITY_NOT_FOUND"


# --- conversations with personalities ---------------------------------------------------


async def new_conversation(client: httpx.AsyncClient, **body: object) -> dict[str, object]:
    response = await client.post("/api/conversations", json={"model": "m", **body})
    assert response.status_code == 201, response.text
    return dict(response.json())


async def send(client: httpx.AsyncClient, conversation_id: object) -> None:
    response = await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": "hola"}
    )
    assert response.status_code == 200


async def test_new_conversation_defaults_to_mentor_ctf(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation = await new_conversation(client)

    assert conversation["personality"] == {
        "id": DEFAULT_PERSONALITY_ID,
        "name": "Mentor CTF",
        "icon": "flag",
    }
    await send(client, conversation["id"])
    system = fake_llm.calls[-1][1][0]
    assert system.role == "system"
    assert system.content.startswith(BASE_PROMPT + PERSONALITY_HEADER)
    assert "mentor de CTF" in system.content
    assert fake_llm.params[-1] is not None and fake_llm.params[-1].temperature == 0.5


async def test_unknown_personality_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/conversations", json={"model": "m", "personality_id": "builtin-nope"}
    )

    assert code(response) == "PERSONALITY_NOT_FOUND"


async def test_snapshot_is_immutable_after_editing_or_deleting_the_personality(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    mine = await create(client, system_prompt="Responde como un pirata.")
    conversation = await new_conversation(client, personality_id=mine["id"])

    await client.patch(
        f"/api/personalities/{mine['id']}",
        json={"system_prompt": "Responde como un robot.", "temperature": 1.9, "name": "Otra"},
    )
    await send(client, conversation["id"])
    assert "pirata" in fake_llm.calls[-1][1][0].content
    assert "robot" not in fake_llm.calls[-1][1][0].content
    assert fake_llm.params[-1] is not None and fake_llm.params[-1].temperature == 0.1

    await client.delete(f"/api/personalities/{mine['id']}")
    await send(client, conversation["id"])
    assert "pirata" in fake_llm.calls[-1][1][0].content
    detail = (await client.get(f"/api/conversations/{conversation['id']}")).json()
    assert detail["personality"] == {"id": None, "name": "Mi pentester", "icon": "crosshair"}


async def test_personality_default_model_is_used_when_none_is_sent(
    client: httpx.AsyncClient,
) -> None:
    mine = await create(client, default_model="groq/openai/gpt-oss-120b")

    response = await client.post("/api/conversations", json={"personality_id": mine["id"]})

    assert response.json()["model"] == "groq/openai/gpt-oss-120b"


async def test_conversation_patch_cannot_change_the_personality(
    client: httpx.AsyncClient,
) -> None:
    conversation = await new_conversation(client)

    response = await client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"title": "t", "personality_id": "builtin-pentester", "system_prompt": "x"},
    )

    detail = (await client.get(f"/api/conversations/{conversation['id']}")).json()
    assert response.status_code == 422
    assert detail["personality"]["id"] == DEFAULT_PERSONALITY_ID


async def test_params_reach_the_provider_payload() -> None:
    from app.adapters.ollama.provider import OllamaProvider
    from app.adapters.openai_compat.provider import OpenAICompatibleProvider
    from app.domain.chat import ChatMessage
    from app.domain.personality import GenerationParams

    seen: list[dict[str, object]] = []

    def ollama(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=b'{"message":{"content":"a"},"done":true}\n')

    def cloud(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        chunk = {"choices": [{"delta": {"content": "a"}, "finish_reason": "stop"}]}
        return httpx.Response(200, content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")

    params = GenerationParams(temperature=0.2, top_p=0.9, num_ctx=4096)
    msgs = [ChatMessage(role="user", content="x")]
    o = OllamaProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(ollama), base_url="http://o")
    )
    c = OpenAICompatibleProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(cloud), base_url="http://c"), "groq"
    )
    [_ async for _ in o.stream_chat("m", msgs, params)]
    [_ async for _ in c.stream_chat("m", msgs, params)]

    assert seen[0]["options"] == {"temperature": 0.2, "top_p": 0.9, "num_ctx": 4096}
    assert (seen[1]["temperature"], seen[1]["top_p"]) == (0.2, 0.9)
    assert "num_ctx" not in seen[1]  # not supported by the OpenAI-compatible API: dropped


async def test_no_params_sends_no_options() -> None:
    from app.adapters.ollama.provider import OllamaProvider
    from app.domain.chat import ChatMessage

    seen: list[dict[str, object]] = []

    def ollama(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=b'{"message":{"content":"a"},"done":true}\n')

    o = OllamaProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(ollama), base_url="http://o")
    )
    [_ async for _ in o.stream_chat("m", [ChatMessage(role="user", content="x")])]

    assert "options" not in seen[0]


async def test_new_conversation_rejects_snapshot_fields(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/conversations", json={"model": "m", "system_prompt": "sin reglas"}
    )

    assert response.status_code == 422
