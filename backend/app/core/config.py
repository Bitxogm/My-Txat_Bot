import ipaddress
import re
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

MIN_SESSION_SECRET_LENGTH = 32

# Provider names go into environment variable names (PROVIDER_<NAME>_...): letters and digits.
PROVIDER_NAME = re.compile(r"^[a-z0-9]{1,20}$")
RESERVED_PROVIDER_NAMES = frozenset({"ollama"})
DEFAULT_PROVIDER_CONTEXT_TOKENS = 6000
_PROVIDER_PREFIX = "provider_"


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool(value: str, key: str) -> bool:
    lowered = value.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("", "0", "false", "no", "off"):
        return False
    raise ValueError(f"{key.upper()} debe ser true o false")


_TAILSCALE = ipaddress.ip_network("100.64.0.0/10")


def _is_private_host(host: str) -> bool:
    """Loopback, private (RFC 1918), Tailscale (100.64.0.0/10, *.ts.net) or a single-label
    name such as host.docker.internal or localhost: never a public internet host."""
    host = host.lower().rstrip(".")
    if host in ("localhost", "host.docker.internal") or host.endswith((".ts.net", ".local")):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host  # single-label LAN name
    return address.is_loopback or address.is_private or address in _TAILSCALE


def _checked_url(name: str, url: str, has_key: bool, local: bool) -> str:
    parts = urlsplit(url)
    variable = f"PROVIDER_{name.upper()}_BASE_URL"
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"{variable} debe ser una URL http(s) con host")
    if parts.username or parts.password:
        raise ValueError(f"{variable} no puede llevar usuario ni contraseña; usa _API_KEY")
    private = _is_private_host(parts.hostname)
    if local and not private:
        # _LOCAL hides the "leaves your network" warnings: only for servers that don't leave it.
        raise ValueError(
            f"PROVIDER_{name.upper()}_LOCAL=true solo para servidores en esta máquina, la LAN o"
            f" Tailscale; {variable} apunta a un host público"
        )
    if has_key and parts.scheme == "http" and not private:
        raise ValueError(f"{variable} usa http con clave hacia un host público: usa https")
    return url


class ProviderConfig(BaseModel):
    """One OpenAI-compatible provider (ADR-019): Groq, OpenRouter, LM Studio, llama.cpp..."""

    model_config = ConfigDict(frozen=True)

    name: str
    base_url: str
    api_key: SecretStr = SecretStr("")
    # Allowlist of model ids; empty = every chat model the provider lists.
    models: list[str] = Field(default_factory=list)
    # Model ids that accept images (the OpenAI-style /models list doesn't say).
    vision_models: list[str] = Field(default_factory=list)
    # Budget to fit the history into (ADR-018). For a local server it must match the window the
    # model was loaded with; for Groq's free tier it must stay under its tokens-per-minute limit.
    context_tokens: int = Field(default=DEFAULT_PROVIDER_CONTEXT_TOKENS, ge=1024, le=1_000_000)
    # True when the server runs on this machine (LM Studio, llama.cpp): nothing leaves it, so the
    # app treats its models as local (no "leaves your network" warnings).
    local: bool = False
    # Sent as "reasoning_effort" when set. "none" turns reasoning off on servers that support it
    # (LM Studio with Qwen3.x), like OLLAMA_THINK=false for Ollama: otherwise these models spend
    # minutes and the length budget thinking (in reasoning_content) before the first word.
    # Values depend on the server and model (Groq's gpt-oss: low/medium/high, no "none").
    reasoning_effort: str = Field(default="", pattern=r"^[a-z]{0,16}$")
    # Variable to point at when the key is rejected.
    key_variable: str = ""


class _ProviderVariables(PydanticBaseSettingsSource):
    """Collects every PROVIDER_<NAME>_<FIELD> variable (environment over .env file), which can't
    be declared as fixed fields because the names are chosen by the user."""

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        env: PydanticBaseSettingsSource,
        dotenv: PydanticBaseSettingsSource,
    ) -> None:
        super().__init__(settings_cls)
        self._env = env
        self._dotenv = dotenv

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        found: dict[str, str] = {}
        for source in (self._dotenv, self._env):  # later wins: the environment
            if isinstance(source, EnvSettingsSource | DotEnvSettingsSource):
                for key, value in source.env_vars.items():
                    if key.lower().startswith(_PROVIDER_PREFIX) and value is not None:
                        found[key.lower()] = value
        return {"provider_variables": found}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: float = Field(default=2.0, gt=0)
    ollama_chat_read_timeout_seconds: float = Field(default=300.0, gt=0)
    ollama_think: bool = False
    # Sent as keep_alive with every chat request: how long Ollama keeps the model loaded after
    # answering. Its default (5m) unloads it between questions, and reloading a 9-35B model on
    # an 8 GB GPU takes over a minute. Ollama durations: "30m", "1h", "0" (unload now), "-1".
    ollama_keep_alive: str = Field(default="30m", pattern=r"^-?\d+(ms|s|m|h)?$")
    # Context window (tokens) for local models when the personality doesn't set num_ctx. Ollama's
    # own default (4096) fills up in two or three turns with an image or long answers.
    ollama_num_ctx: int = Field(default=8192, ge=2048, le=131072)
    default_model: str = ""

    # OpenAI-compatible providers (ADR-019): PROVIDERS=groq,lmstudio and, for each one,
    # PROVIDER_<NAME>_BASE_URL, _API_KEY, _MODELS, _VISION_MODELS, _CONTEXT_TOKENS, _LOCAL.
    providers: str = ""
    provider_variables: dict[str, str] = Field(default_factory=dict, exclude=True, repr=False)
    provider_timeout_seconds: float = Field(default=10.0, gt=0)

    # DEPRECATED (ADR-019): the single cloud slot. Used only when PROVIDERS is empty and
    # CLOUD_API_KEY is set; it becomes one provider named CLOUD_NAME (groq).
    cloud_name: str = Field(default="groq", pattern=r"^[a-z0-9-]{1,20}$")
    cloud_base_url: str = "https://api.groq.com/openai/v1"
    cloud_api_key: SecretStr = SecretStr("")
    # Comma-separated allowlist of model ids; empty = every chat model the provider lists.
    cloud_models: str = ""
    cloud_timeout_seconds: float = Field(default=10.0, gt=0)
    # Groq's free tier allows ~8000 tokens per minute: one request can't use more.
    cloud_context_tokens: int = Field(
        default=DEFAULT_PROVIDER_CONTEXT_TOKENS, ge=1024, le=1_000_000
    )
    # Comma-separated cloud model ids that accept images (the OpenAI-style /models list doesn't
    # say). Defaults: Groq's vision models.
    cloud_vision_models: str = (
        "meta-llama/llama-4-scout-17b-16e-instruct,meta-llama/llama-4-maverick-17b-128e-instruct"
    )

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
    # Where uploaded files are stored (a Docker volume in production: ./data -> /app/data).
    upload_dir: str = "./data/uploads"

    @property
    def upload_max_bytes(self) -> int:
        return self.upload_max_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    _providers: list[ProviderConfig] = PrivateAttr(default_factory=list)
    _config_warnings: list[str] = PrivateAttr(default_factory=list)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Right after the init kwargs, so a PROVIDER_VARIABLES variable can't replace the set.
        return (
            init_settings,
            _ProviderVariables(settings_cls, env_settings, dotenv_settings),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    @model_validator(mode="after")
    def _build_providers(self) -> "Settings":
        names = _csv(self.providers.lower())
        if names:
            self._providers = [self._provider(name) for name in names]
            seen = [p.name for p in self._providers]
            duplicated = sorted({n for n in seen if seen.count(n) > 1})
            if duplicated:
                raise ValueError(f"Proveedor repetido en PROVIDERS: {', '.join(duplicated)}")
            if self.cloud_api_key.get_secret_value():
                self._config_warnings.append(
                    "CLOUD_* is ignored because PROVIDERS is set (ADR-019)"
                )
        elif self.cloud_api_key.get_secret_value():
            self._providers = [
                ProviderConfig(
                    name=self.cloud_name,
                    base_url=self.cloud_base_url,
                    api_key=self.cloud_api_key,
                    models=_csv(self.cloud_models),
                    vision_models=_csv(self.cloud_vision_models),
                    context_tokens=self.cloud_context_tokens,
                    key_variable="CLOUD_API_KEY",
                )
            ]
            self._config_warnings.append(
                "CLOUD_* variables are deprecated: use PROVIDERS and PROVIDER_<NAME>_* (ADR-019)"
            )
        # The keys now live in ProviderConfig.api_key (SecretStr): drop the plain-text copies.
        object.__setattr__(self, "provider_variables", {})
        return self

    def _provider(self, name: str) -> ProviderConfig:
        if not PROVIDER_NAME.fullmatch(name) or name in RESERVED_PROVIDER_NAMES:
            raise ValueError(
                f"Nombre de proveedor no válido: {name!r} (solo letras minúsculas y números,"
                " y distinto de 'ollama')"
            )
        prefix = f"{_PROVIDER_PREFIX}{name}_"

        def var(field: str) -> str:
            return self.provider_variables.get(prefix + field, "").strip()

        base_url = var("base_url")
        if not base_url:
            raise ValueError(f"Falta PROVIDER_{name.upper()}_BASE_URL")
        local = _bool(var("local"), prefix + "local")
        api_key = var("api_key")
        context = var("context_tokens")
        return ProviderConfig(
            name=name,
            base_url=_checked_url(name, base_url, bool(api_key), local),
            api_key=SecretStr(api_key),
            models=_csv(var("models")),
            vision_models=_csv(var("vision_models")),
            context_tokens=int(context) if context else DEFAULT_PROVIDER_CONTEXT_TOKENS,
            local=local,
            reasoning_effort=var("reasoning_effort").lower(),
            key_variable=f"PROVIDER_{name.upper()}_API_KEY",
        )

    @property
    def provider_list(self) -> list[ProviderConfig]:
        """Configured OpenAI-compatible providers (the legacy CLOUD_* slot included)."""
        return list(self._providers)

    @property
    def config_warnings(self) -> list[str]:
        """Problems worth logging at startup (deprecated variables...)."""
        return list(self._config_warnings)

    def provider_for(self, model: str) -> ProviderConfig | None:
        """The provider a "<name>/<model id>" belongs to; None for Ollama models."""
        prefix, sep, _ = model.partition("/")
        if not sep:
            return None
        return next((p for p in self._providers if p.name == prefix), None)

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
