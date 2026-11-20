from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class ModelInfo:
    name: str
    size_bytes: int
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    # True when the model runs on a third-party service: messages leave the local network.
    remote: bool = False
