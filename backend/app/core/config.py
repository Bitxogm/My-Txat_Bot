from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: float = Field(default=2.0, gt=0)
    default_model: str = ""

    database_url: str = "sqlite:///./data/txatbot.db"

    auth_username: str = ""
    auth_password_hash: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")

    cors_origins: str = "http://localhost:5173"

    upload_max_mb: int = Field(default=20, gt=0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
