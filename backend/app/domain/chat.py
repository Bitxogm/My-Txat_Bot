from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ImageData:
    """An image for a vision model: already validated and re-encoded (ADR-016)."""

    mime: str
    data: bytes


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str
    images: tuple[ImageData, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelInfo:
    name: str
    size_bytes: int
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    # True when the model runs on a third-party service: messages leave the local network.
    remote: bool = False
    # Accepts images (Ollama "vision" capability, or PROVIDER_<NAME>_VISION_MODELS).
    vision: bool = False
    # Where it runs: "ollama" or the name of an OpenAI-compatible provider (ADR-019).
    provider: str = "ollama"
