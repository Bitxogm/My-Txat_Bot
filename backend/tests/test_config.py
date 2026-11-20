from app.core.config import Settings


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(cors_origins=" http://a.test , ,http://b.test", _env_file=None)  # type: ignore[call-arg]

    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_docs_disabled_in_production() -> None:
    from app.main import create_app

    app = create_app(Settings(app_env="production", _env_file=None))  # type: ignore[call-arg]

    assert app.docs_url is None
    assert app.openapi_url is None
