from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.adapters.ollama.provider import OllamaProvider
from app.adapters.openai_compat.provider import OpenAICompatibleProvider
from app.api.generation import context_for
from app.core.errors import ContextTooLongError
from app.domain.attachment import Attachment
from app.domain.chat import ChatMessage, ImageData
from app.domain.context import (
    Turn,
    fit_history,
    image_size,
    image_tokens,
    message_tokens,
    text_tokens,
)
from app.domain.personality import GenerationParams
from tests.conftest import FakeLLMProvider, make_settings
from tests.image_fixtures import png

SYSTEM = "s" * 300  # ~100 tokens


def file(text: str, name: str = "log.txt") -> Attachment:
    return Attachment(
        id=name,
        conversation_id="c",
        message_id=1,
        filename=name,
        mime="text/plain",
        kind="text",
        size_bytes=len(text),
        sha256="",
        storage_key="k" * 32,
        text=text,
        truncated=False,
        created_at=datetime.now(UTC),
    )


def chat(n: int, chars: int = 3000) -> list[Turn]:
    turns: list[Turn] = []
    for i in range(n):
        turns.append(Turn(role="user", text=f"pregunta {i} " + "u" * 30))
        turns.append(Turn(role="assistant", text=f"respuesta {i} " + "a" * chars))
    return turns


def total(messages: list[ChatMessage]) -> int:
    return sum(message_tokens(m) for m in messages)


# --- estimates -----------------------------------------------------------------------------


def test_estimates() -> None:
    assert text_tokens("a" * 30) == 10
    assert image_size(png(1568, 784)) == (1568, 784)
    assert image_tokens(ImageData(mime="image/png", data=png(1568, 784))) == 56 * 28


def test_image_size_of_a_jpeg() -> None:
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (300, 200)).save(out, format="JPEG")

    assert image_size(out.getvalue()) == (300, 200)
    assert image_size(b"not an image") is None


# --- fitting -------------------------------------------------------------------------------


def test_everything_is_kept_when_it_fits() -> None:
    fitted = fit_history(SYSTEM, chat(3, 300), Turn(role="user", text="hola"), 8192)

    assert len(fitted.messages) == 1 + 6 + 1
    assert fitted.dropped_turns == 0


def test_long_conversations_drop_the_oldest_turns_and_say_so() -> None:
    budget = 4096
    fitted = fit_history(SYSTEM, chat(10), Turn(role="user", text="sigue"), budget)

    messages = fitted.messages
    assert fitted.dropped_turns > 0
    assert total(messages) <= budget - 1024  # the reply's reserve is left free
    assert messages[0].role == "system" and messages[-1].content == "sigue"
    assert messages[1].role == "user"  # never opens with an orphan reply
    assert "se han omitido" in messages[1].content
    assert "respuesta 9" in messages[-2].content  # the newest turns survive


def test_old_images_go_before_old_turns() -> None:
    image = ImageData(mime="image/png", data=png(1568, 1568))  # ~3136 tokens
    earlier = [
        Turn(role="user", text="mira", images=(image,)),
        Turn(role="assistant", text="veo un gato"),
    ]

    fitted = fit_history(SYSTEM, earlier, Turn(role="user", text="¿y el fondo?"), 4096)

    assert fitted.dropped_images == 1 and fitted.dropped_turns == 0
    assert [m.content for m in fitted.messages[1:]] == ["mira", "veo un gato", "¿y el fondo?"]
    assert all(not m.images for m in fitted.messages)


def test_old_files_lose_their_content_before_the_turn_is_dropped() -> None:
    earlier = [
        Turn(role="user", text="analiza", files=[file("x" * 12_000)]),
        Turn(role="assistant", text="hecho"),
    ]

    fitted = fit_history(SYSTEM, earlier, Turn(role="user", text="resume"), 4096)

    assert fitted.omitted_files == 1 and fitted.dropped_turns == 0
    assert 'contenido="omitido por espacio"' in fitted.messages[1].content
    assert "xxxx" not in fitted.messages[1].content


def test_files_of_the_new_message_are_cut_to_fit() -> None:
    current = Turn(role="user", text="analiza", files=[file("y" * 12_000)])

    fitted = fit_history(SYSTEM, [], current, 4096)

    newest = fitted.messages[-1]
    assert 'recortado="sí"' in newest.content
    assert total(fitted.messages) <= 4096 - 1024


def test_a_message_that_can_never_fit_is_refused() -> None:
    with pytest.raises(ContextTooLongError):
        fit_history(SYSTEM, [], Turn(role="user", text="z" * 20_000), 4096)

    image = ImageData(mime="image/png", data=png(1568, 1568))
    with pytest.raises(ContextTooLongError):
        fit_history(SYSTEM, [], Turn(role="user", text="mira", images=(image,) * 2), 4096)


# --- budget per model ------------------------------------------------------------------------


def test_local_models_get_a_bigger_window_unless_the_personality_sets_one() -> None:
    settings = make_settings(ollama_num_ctx=8192, cloud_api_key="k", cloud_context_tokens=32768)

    assert context_for("qwen3.5:9b", GenerationParams(), settings) == (
        8192,
        GenerationParams(num_ctx=8192),
    )
    own = GenerationParams(temperature=0.2, num_ctx=4096)
    assert context_for("qwen3.5:9b", own, settings) == (4096, own)
    assert context_for("groq/llama", own, settings) == (32768, own)  # num_ctx: provider's own


# --- routes ----------------------------------------------------------------------------------


async def test_a_long_conversation_keeps_working(
    app: FastAPI, client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    app.state.settings = make_settings(ollama_num_ctx=4096)
    conversation_id = (await client.post("/api/conversations", json={"model": "m"})).json()["id"]
    fake_llm.chunks = ["r" * 4000]  # long replies, like the Mentor's

    for i in range(8):
        response = await client.post(
            f"/api/conversations/{conversation_id}/messages", json={"content": f"turno {i}"}
        )
        assert response.status_code == 200

    sent = fake_llm.calls[-1][1]
    assert total(sent) <= 4096
    assert sent[-1].content == "turno 7"
    assert "se han omitido" in sent[1].content
    assert fake_llm.params[-1] is not None and fake_llm.params[-1].num_ctx == 4096


async def test_a_message_too_long_is_refused_and_not_stored(
    app: FastAPI, client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    app.state.settings = make_settings(ollama_num_ctx=2048)
    conversation_id = (await client.post("/api/conversations", json={"model": "m"})).json()["id"]

    response = await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": "x" * 50_000}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CONTEXT_TOO_LONG"
    assert fake_llm.calls == []
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"] == []


async def test_stateless_chat_is_fitted_too(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    history = [
        {"role": role, "content": ("u" if role == "user" else "a") * 6000}
        for _ in range(10)
        for role in ("user", "assistant")
    ]
    history.append({"role": "user", "content": "última"})

    response = await client.post("/api/chat", json={"model": "m", "messages": history})

    assert response.status_code == 200
    assert total(fake_llm.calls[-1][1]) <= 8192
    assert fake_llm.calls[-1][1][-1].content == "última"


# --- adapters --------------------------------------------------------------------------------


async def test_ollama_context_overflow_is_a_clear_error() -> None:
    body = (
        '{"error":"{\\"error\\":{\\"code\\":400,\\"message\\":\\"request (4114 tokens) exceeds'
        ' the available context size (4096 tokens)\\",'
        '\\"type\\":\\"exceed_context_size_error\\"}}"}'
    )
    provider = OllamaProvider(
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(400, text=body)),
            base_url="http://o.test",
        )
    )

    with pytest.raises(ContextTooLongError):
        [c async for c in provider.stream_chat("m", [ChatMessage(role="user", content="x")])]


async def test_cloud_context_overflow_is_a_clear_error() -> None:
    body = '{"error":{"message":"too long","code":"context_length_exceeded"}}'
    provider = OpenAICompatibleProvider(
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(400, text=body)),
            base_url="http://c.test",
        ),
        "groq",
    )

    with pytest.raises(ContextTooLongError):
        [c async for c in provider.stream_chat("m", [ChatMessage(role="user", content="x")])]
