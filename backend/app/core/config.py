from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SESSION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: float = Field(default=2.0, gt=0)
    ollama_chat_read_timeout_seconds: float = Field(default=300.0, gt=0)
    ollama_think: bool = False
    default_model: str = ""

    # Optional cloud provider with an OpenAI-compatible API (Groq by default). Off without a key.
    cloud_name: str = Field(default="groq", pattern=r"^[a-z0-9-]{1,20}$")
    cloud_base_url: str = "https://api.groq.com/openai/v1"
    cloud_api_key: SecretStr = SecretStr("")
    # Comma-separated allowlist of model ids; empty = every chat model the provider lists.
    cloud_models: str = ""
    cloud_timeout_seconds: float = Field(default=10.0, gt=0)

    database_url: str = "sqlite:///./data/txatbot.db"

    auth_username: str = ""
    auth_password_hash: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")
    session_ttl_hours: int = Field(default=72, gt=0)
    # Only set to true when the app is served over HTTPS; browsers drop Secure cookies on HTTP.
    cookie_secure: bool = False
    login_max_failures: int = Field(default=5, gt=0)
    login_window_seconds: int = Field(default=300, gt=0)

    cors_origins: str = "http://localhost:5173"

    upload_max_mb: int = Field(default=20, gt=0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def cloud_enabled(self) -> bool:
        return bool(self.cloud_api_key.get_secret_value())

    @property
    def cloud_model_list(self) -> list[str]:
        return [m.strip() for m in self.cloud_models.split(",") if m.strip()]

    @property
    def auth_configured(self) -> bool:
        return bool(
            self.auth_username
            and self.auth_password_hash.get_secret_value()
            and len(self.session_secret.get_secret_value()) >= MIN_SESSION_SECRET_LENGTH
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
