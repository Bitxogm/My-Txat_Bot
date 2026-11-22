import logging
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.adapters.llm_factory import build_llm_provider
from app.adapters.openai_compat.provider import (
    OpenAICompatibleProvider,
    build_openai_compatible_client,
)
from app.api.generation import context_for
from app.core.config import Settings
from app.core.errors import ModelUnavailableError
from app.domain.chat import ChatMessage
from app.domain.personality import GenerationParams
from tests.conftest import make_settings

LMSTUDIO = {
    "provider_lmstudio_base_url": "http://127.0.0.1:1234/v1",
    "provider_lmstudio_local": "true",
    "provider_lmstudio_context_tokens": "16384",
}
GROQ = {
    "provider_groq_base_url": "https://api.groq.com/openai/v1",
    "provider_groq_api_key": "gsk-test",
    "provider_groq_models": "openai/gpt-oss-120b, qwen/qwen3.8-27b",
    "provider_groq_vision_models": "meta-llama/llama-4-scout-17b-16e-instruct",
}


def settings(**overrides: object) -> Settings:
    return make_settings(provider_variables={**GROQ, **LMSTUDIO}, **overrides)


# --- configuration ---------------------------------------------------------------------------


def test_several_providers_are_read() -> None:
    groq, lmstudio = settings(providers="groq,lmstudio").provider_list

    assert groq.name == "groq" and groq.api_key.get_secret_value() == "gsk-test"
    assert groq.models == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
    assert groq.context_tokens == 6000 and not groq.local
    assert lmstudio.local and lmstudio.context_tokens == 16384
    assert lmstudio.api_key.get_secret_value() == ""


def test_variables_come_from_the_environment_and_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PROVIDERS=lmstudio\n"
        "PROVIDER_LMSTUDIO_BASE_URL=http://from-file:1234/v1\n"
        "PROVIDER_LMSTUDIO_CONTEXT_TOKENS=8192\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROVIDER_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")

    [lmstudio] = Settings(_env_file=env_file).provider_list  # type: ignore[call-arg]

    assert lmstudio.base_url == "http://127.0.0.1:1234/v1"  # the environment wins
    assert lmstudio.context_tokens == 8192


def test_legacy_cloud_variables_become_a_groq_provider_with_a_warning() -> None:
    config = make_settings(cloud_api_key="gsk-old", cloud_models="openai/gpt-oss-120b")

    [groq] = config.provider_list
    assert (groq.name, groq.context_tokens, groq.key_variable) == ("groq", 6000, "CLOUD_API_KEY")
    assert groq.vision_models  # the old Groq vision defaults
    assert any("deprecated" in w for w in config.config_warnings)


def test_providers_win_over_legacy_variables() -> None:
    config = settings(providers="lmstudio", cloud_api_key="gsk-old")

    assert [p.name for p in config.provider_list] == ["lmstudio"]
    assert any("ignored" in w for w in config.config_warnings)


def test_no_providers_means_ollama_only() -> None:
    assert make_settings().provider_list == []


@pytest.mark.parametrize(
    ("providers", "variables", "message"),
    [
        ("lm-studio", {}, "no válido"),
        ("ollama", {}, "no válido"),
        ("groq,groq", GROQ, "repetido"),
        ("nada", {}, "PROVIDER_NADA_BASE_URL"),
        ("lmstudio", {**LMSTUDIO, "provider_lmstudio_local": "quizás"}, "true o false"),
    ],
)
def test_bad_configurations_fail_at_startup(
    providers: str, variables: dict[str, str], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        make_settings(providers=providers, provider_variables=variables)


def test_factory_logs_the_deprecation(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        build_llm_provider(make_settings(cloud_api_key="gsk-old"))

    assert "deprecated" in caplog.text
    assert "gsk-old" not in caplog.text  # never the key


# --- behaviour -------------------------------------------------------------------------------


def test_no_key_no_authorization_header() -> None:
    keyless = build_openai_compatible_client("http://127.0.0.1:1234/v1", "", 5)
    keyed = build_openai_compatible_client("https://x/v1", "k", 5)

    assert "authorization" not in keyless.headers
    assert keyed.headers["authorization"] == "Bearer k"


async def test_local_providers_list_local_models() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [{"id": "qwen3.6-35b-a3b"}]})
        ),
        base_url="http://127.0.0.1:1234/v1",
    )

    [model] = await OpenAICompatibleProvider(client, "lmstudio", local=True).list_models()

    assert (model.remote, model.provider) == (False, "lmstudio")


async def test_rejected_key_names_the_right_variable() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(401)), base_url="http://x/v1"
    )
    provider = OpenAICompatibleProvider(client, "openrouter")

    with pytest.raises(ModelUnavailableError, match="PROVIDER_OPENROUTER_API_KEY"):
        await provider.list_models()


def test_context_budget_per_provider() -> None:
    config = settings(providers="groq,lmstudio", ollama_num_ctx=8192)
    personality = GenerationParams(temperature=0.3)

    assert context_for("groq/openai/gpt-oss-120b", personality, config) == (6000, personality)
    assert context_for("lmstudio/qwen3.6", personality, config) == (16384, personality)
    assert context_for("qwen3.5:9b", personality, config)[0] == 8192
    # An Ollama model with a namespace is not a provider model.
    assert context_for("hf.co/user/model", personality, config)[0] == 8192


async def test_models_are_routed_by_provider_prefix() -> None:
    seen: dict[str, list[str]] = {"groq": [], "lmstudio": [], "ollama": []}

    def handler(name: str):  # type: ignore[no-untyped-def]
        def respond(request: httpx.Request) -> httpx.Response:
            seen[name].append(request.url.path)
            if request.url.path.endswith("/models"):
                model_id = "openai/gpt-oss-120b" if name == "groq" else f"{name}-model"
                return httpx.Response(200, json={"data": [{"id": model_id}]})
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]})
            if request.url.path == "/api/show":
                return httpx.Response(200, json={"capabilities": ["completion"]})
            body = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
            return httpx.Response(200, content=body)

        return respond

    llm, clients = build_llm_provider(settings(providers="groq,lmstudio"))
    for client in clients:
        name = (
            "ollama"
            if "11434" in str(client.base_url)
            else ("lmstudio" if "1234" in str(client.base_url) else "groq")
        )
        client._transport = httpx.MockTransport(handler(name))

    models = {m.name: (m.provider, m.remote) for m in await llm.list_models()}
    reply = [
        c
        async for c in llm.stream_chat(
            "lmstudio/lmstudio-model", [ChatMessage(role="user", content="hola")]
        )
    ]

    assert models == {
        "qwen3.5:9b": ("ollama", False),
        "groq/openai/gpt-oss-120b": ("groq", True),  # allowed by PROVIDER_GROQ_MODELS
        "lmstudio/lmstudio-model": ("lmstudio", False),
    }
    assert reply == ["ok"]
    assert seen["lmstudio"][-1].endswith("/chat/completions")
    assert not any(p.endswith("/chat/completions") for p in seen["groq"])


# --- hardening (seguridad-web review) --------------------------------------------------------


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        (  # a cloud URL can't be "local": that would hide the privacy warnings
            {"provider_x_base_url": "https://api.groq.com/openai/v1", "provider_x_local": "true"},
            "host público",
        ),
        (  # a key never travels over plain http to the internet
            {"provider_x_base_url": "http://api.example.com/v1", "provider_x_api_key": "k"},
            "usa https",
        ),
        ({"provider_x_base_url": "ftp://127.0.0.1/v1"}, "URL http"),
        ({"provider_x_base_url": "https://user:pass@example.com/v1"}, "usuario ni contraseña"),
    ],
)
def test_unsafe_provider_urls_fail_at_startup(variables: dict[str, str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        make_settings(providers="x", provider_variables=variables)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:1234/v1",
        "http://localhost:1234/v1",
        "http://host.docker.internal:1234/v1",
        "http://192.168.1.20:1234/v1",
        "http://100.101.102.103:1234/v1",
        "http://workstation.tailnet-name.ts.net:1234/v1",
    ],
)
def test_local_providers_on_this_machine_lan_or_tailscale(url: str) -> None:
    [provider] = make_settings(
        providers="lmstudio",
        provider_variables={"provider_lmstudio_base_url": url, "provider_lmstudio_local": "true"},
    ).provider_list

    assert provider.local


def test_plain_text_keys_are_not_kept_in_the_settings() -> None:
    config = settings(providers="groq")

    assert config.provider_variables == {}
    assert "gsk-test" not in repr(vars(config))
    assert config.provider_list[0].api_key.get_secret_value() == "gsk-test"


def test_a_provider_variables_env_var_cannot_replace_the_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROVIDERS", "lmstudio")
    monkeypatch.setenv("PROVIDER_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv(
        "PROVIDER_VARIABLES", '{"provider_lmstudio_base_url": "https://evil.example/v1"}'
    )

    [provider] = Settings(_env_file=None).provider_list  # type: ignore[call-arg]

    assert provider.base_url == "http://127.0.0.1:1234/v1"


async def test_ollama_models_shadowed_by_a_provider_are_hidden(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.adapters.routing import RoutingLLMProvider
    from app.domain.chat import ModelInfo
    from tests.conftest import FakeLLMProvider

    ollama, remote = FakeLLMProvider(), FakeLLMProvider()
    ollama.models = [
        ModelInfo(name="mannix/llama3", size_bytes=1),
        ModelInfo(name="hf.co/user/model", size_bytes=1),
        ModelInfo(name="qwen3.5:9b", size_bytes=1),
    ]
    remote.models = []
    remote.name = "mannix"  # type: ignore[attr-defined]

    with caplog.at_level(logging.WARNING):
        names = [m.name for m in await RoutingLLMProvider(ollama, [remote]).list_models()]  # type: ignore[list-item]

    assert names == ["hf.co/user/model", "qwen3.5:9b"]
    assert "mannix" in caplog.text
