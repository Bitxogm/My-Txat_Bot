import base64
import io
import json

import httpx
import pytest
from PIL import Image

from app.adapters.files.isolated import run_isolated
from app.adapters.ollama.provider import OllamaProvider
from app.adapters.openai_compat.provider import OpenAICompatibleProvider
from app.adapters.routing import RoutingLLMProvider
from app.core.errors import ModelNotFoundError
from app.domain.attachment import MAX_IMAGES_PER_REQUEST
from app.domain.chat import ChatMessage, ImageData
from tests.conftest import FakeLLMProvider
from tests.image_fixtures import (
    animated_gif,
    jpeg_with_comment,
    jpeg_with_exif,
    noisy_png,
    png,
    png_claiming,
    png_header_over_pcd,
    png_with_icc,
    webp,
)


async def new_conversation(client: httpx.AsyncClient, model: str = "m") -> str:
    response = await client.post("/api/conversations", json={"model": model})
    return str(response.json()["id"])


async def upload(client: httpx.AsyncClient, conversation_id: str, name: str, data: bytes) -> dict:
    response = await client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={"file": (name, data, "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def content(client: httpx.AsyncClient, conversation_id: str, attachment_id: str):
    return await client.get(
        f"/api/conversations/{conversation_id}/attachments/{attachment_id}/content"
    )


# --- upload ------------------------------------------------------------------------------


async def test_jpeg_is_reencoded_without_metadata(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client)
    original = jpeg_with_exif()
    assert b"CamaraSecreta" in original

    attachment = await upload(client, conversation_id, "foto.jpg", original)
    served = await content(client, conversation_id, attachment["id"])

    assert attachment["kind"] == "image" and attachment["mime"] == "image/jpeg"
    assert served.status_code == 200
    assert b"CamaraSecreta" not in served.content
    with Image.open(io.BytesIO(served.content)) as image:
        assert not image.getexif()
        assert image.size == (40, 30)


async def test_large_images_are_scaled_down(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client)

    attachment = await upload(client, conversation_id, "captura.png", png(3200, 1600))
    served = await content(client, conversation_id, attachment["id"])

    with Image.open(io.BytesIO(served.content)) as image:
        assert image.size == (1568, 784)
        assert image.format == "PNG"  # screenshots stay lossless (readable text)


async def test_formats_are_normalized(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client)

    transparent = await upload(client, conversation_id, "a.webp", png(mode="RGBA"))
    gif = await upload(client, conversation_id, "b.gif", animated_gif())
    photo = await upload(client, conversation_id, "c.webp", webp())

    assert transparent["mime"] == "image/png"
    assert gif["mime"] == "image/png"  # first frame only
    assert photo["mime"] == "image/jpeg"


async def test_bombs_and_broken_images_are_422(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client)

    bomb = await client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={"file": ("bomba.png", png_claiming(30_000, 30_000))},
    )
    broken = await client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={"file": ("rota.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)},
    )

    assert bomb.status_code == 422 and "píxeles" in bomb.json()["error"]["message"]
    assert broken.status_code == 422 and broken.json()["error"]["code"] == "UNREADABLE_FILE"


async def test_comments_and_icc_profiles_do_not_survive(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client)
    secret = b"GPS 40.4168,-3.7038 casa"

    photo = await upload(client, conversation_id, "a.jpg", jpeg_with_comment(secret))
    icc = await upload(client, conversation_id, "b.png", png_with_icc(b"MiPortatil"))
    photo_bytes = (await content(client, conversation_id, photo["id"])).content
    icc_bytes = (await content(client, conversation_id, icc["id"])).content

    assert secret not in photo_bytes and b"MiPortatil" not in icc_bytes
    with Image.open(io.BytesIO(photo_bytes)) as image:
        assert "comment" not in image.info
    with Image.open(io.BytesIO(icc_bytes)) as image:
        assert "icc_profile" not in image.info


async def test_only_the_announced_decoder_is_used(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client)

    response = await client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={"file": ("x.png", png_header_over_pcd())},
    )

    assert response.status_code == 422


async def test_heavy_lossless_images_become_jpeg(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client)

    attachment = await upload(client, conversation_id, "ruido.png", noisy_png())

    assert attachment["mime"] == "image/jpeg"


def _environment_keys() -> list[str]:
    import os

    return sorted(os.environ)


async def test_the_parser_process_gets_no_secrets(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)

    assert await run_isolated(_environment_keys, time_limit=30) == []


# --- serving -------------------------------------------------------------------------------


async def test_content_is_served_safely_and_only_for_images(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client)
    other = await new_conversation(client)
    image = await upload(client, conversation_id, "a.png", png())
    text = await upload(client, conversation_id, "a.txt", b"hola")

    served = await content(client, conversation_id, image["id"])

    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in served.headers["content-security-policy"]
    assert served.headers["cache-control"] == "private, no-cache"
    assert (await content(client, conversation_id, text["id"])).status_code == 404
    assert (await content(client, other, image["id"])).status_code == 404


async def test_content_requires_a_session(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get(
        f"/api/conversations/{'a' * 32}/attachments/{'b' * 32}/content"
    )

    assert response.status_code == 401


# --- sending -------------------------------------------------------------------------------


async def test_images_need_a_vision_model(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    conversation_id = await new_conversation(client)
    image = await upload(client, conversation_id, "a.png", png())

    response = await client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "qué ves", "attachment_ids": [image["id"]]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MODEL_WITHOUT_VISION"
    assert fake_llm.calls == []
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"] == []  # nothing stored; the image is still pending


async def test_vision_model_gets_the_pixels_and_the_name(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.vision_models.add("m")
    conversation_id = await new_conversation(client)
    image = await upload(client, conversation_id, "captura.png", png())
    served = (await content(client, conversation_id, image["id"])).content

    response = await client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "qué ves", "attachment_ids": [image["id"]]},
    )

    assert response.status_code == 200
    user_turn = fake_llm.calls[-1][1][-1]
    assert user_turn.images == (ImageData(mime="image/png", data=served),)
    assert '<fichero nombre="captura.png" tipo="imagen"/>' in user_turn.content
    assert fake_llm.calls[-1][1][0].images == ()  # never in the system prompt


async def test_only_the_newest_images_are_resent(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.vision_models.add("m")
    conversation_id = await new_conversation(client)
    for turn in range(MAX_IMAGES_PER_REQUEST + 2):
        image = await upload(client, conversation_id, f"{turn}.png", png(8 + turn, 8))
        await client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": f"turno {turn}", "attachment_ids": [image["id"]]},
        )

    history = fake_llm.calls[-1][1]
    with_images = [m for m in history if m.images]
    assert len(with_images) == MAX_IMAGES_PER_REQUEST
    assert with_images[-1] is history[-1]
    assert "turno 0" not in with_images[0].content and "turno 1" not in with_images[0].content


async def test_switching_to_a_text_model_drops_earlier_images(
    client: httpx.AsyncClient, fake_llm: FakeLLMProvider
) -> None:
    fake_llm.vision_models.add("vision")
    conversation_id = await new_conversation(client, model="vision")
    image = await upload(client, conversation_id, "a.png", png())
    await client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "uno", "attachment_ids": [image["id"]], "model": "vision"},
    )

    response = await client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "dos", "model": "texto"},
    )

    assert response.status_code == 200
    assert all(not m.images for m in fake_llm.calls[-1][1])
    assert 'tipo="imagen"' in fake_llm.calls[-1][1][1].content


# --- adapters ------------------------------------------------------------------------------

PIXELS = ImageData(mime="image/png", data=b"\x89PNGfake")


async def test_ollama_sends_base64_images_and_reads_capabilities() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion", "vision"]})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen", "digest": "d1"}]})
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=b'{"message":{"content":"ok"},"done":true}\n')

    provider = OllamaProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://o.test")
    )
    message = ChatMessage(role="user", content="mira", images=(PIXELS,))

    assert [c async for c in provider.stream_chat("qwen", [message])] == ["ok"]
    assert seen[0]["messages"][0]["images"] == [base64.b64encode(PIXELS.data).decode()]
    assert await provider.supports_vision("qwen") is True
    assert (await provider.list_models())[0].vision is True


async def test_ollama_without_capabilities_means_no_vision() -> None:
    provider = OllamaProvider(
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(404)), base_url="http://o.test"
        )
    )

    assert await provider.supports_vision("llama3") is False


async def test_openai_compat_sends_data_urls_to_vision_models() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "scout"}, {"id": "texto"}]})
        seen.append(json.loads(request.content))
        body = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, content=body)

    provider = OpenAICompatibleProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://c.test/v1"),
        "groq",
        vision_models=["scout"],
    )
    message = ChatMessage(role="user", content="mira", images=(PIXELS,))

    assert [c async for c in provider.stream_chat("scout", [message])] == ["ok"]
    parts = seen[0]["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "mira"}
    encoded = base64.b64encode(PIXELS.data).decode()
    assert parts[1]["image_url"]["url"] == f"data:image/png;base64,{encoded}"
    assert {m.name: m.vision for m in await provider.list_models()} == {
        "scout": True,
        "texto": False,
    }


async def test_cloud_allowlist_also_limits_vision_and_chat() -> None:
    provider = OpenAICompatibleProvider(
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(500)), base_url="http://c.test"
        ),
        "groq",
        allowed_models=["texto"],
        vision_models=["scout"],
    )

    assert await provider.supports_vision("scout") is False
    with pytest.raises(ModelNotFoundError):
        [c async for c in provider.stream_chat("scout", [ChatMessage(role="user", content="x")])]


async def test_ollama_rereads_capabilities_after_a_new_pull() -> None:
    shows: list[str] = []
    digest = {"value": "old"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            shows.append(digest["value"])
            caps = ["completion", "vision"] if digest["value"] == "new" else ["completion"]
            return httpx.Response(200, json={"capabilities": caps})
        return httpx.Response(200, json={"models": [{"name": "m", "digest": digest["value"]}]})

    provider = OllamaProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://o.test")
    )
    assert (await provider.list_models())[0].vision is False
    assert await provider.supports_vision("m") is False  # cached, no new request

    digest["value"] = "new"
    assert (await provider.list_models())[0].vision is True
    assert await provider.supports_vision("m") is True
    assert shows == ["old", "new"]


async def test_routing_asks_the_right_provider() -> None:
    local, remote = FakeLLMProvider(), FakeLLMProvider()
    local.vision_models.add("qwen")
    remote.vision_models.add("scout")
    remote.name = "groq"  # type: ignore[attr-defined]
    routing = RoutingLLMProvider(local, [remote])  # type: ignore[list-item]

    assert await routing.supports_vision("qwen") is True
    assert await routing.supports_vision("groq/scout") is True
    assert await routing.supports_vision("groq/texto") is False
