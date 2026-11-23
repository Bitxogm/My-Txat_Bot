import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(cors_origins=" http://a.test , ,http://b.test", _env_file=None)  # type: ignore[call-arg]

    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_docs_disabled_in_production() -> None:
    from app.main import create_app

    app = create_app(Settings(app_env="production", _env_file=None))  # type: ignore[call-arg]

    assert app.docs_url is None
    assert app.openapi_url is None


def test_ollama_keep_alive_defaults_to_thirty_minutes() -> None:
    assert Settings(_env_file=None).ollama_keep_alive == "30m"  # type: ignore[call-arg]


@pytest.mark.parametrize("value", ["1h", "0", "-1", "90s", "300"])
def test_ollama_keep_alive_accepts_ollama_durations(value: str) -> None:
    settings = Settings(ollama_keep_alive=value, _env_file=None)  # type: ignore[call-arg]

    assert settings.ollama_keep_alive == value


@pytest.mark.parametrize("value", ["", "media hora", "30 m", "1d"])
def test_ollama_keep_alive_rejects_other_values(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(ollama_keep_alive=value, _env_file=None)  # type: ignore[call-arg]
