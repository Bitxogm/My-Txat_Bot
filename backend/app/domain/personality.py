from dataclasses import dataclass
from datetime import datetime

DEFAULT_PERSONALITY_ID = "builtin-mentor-ctf"

# Parameter ranges, validated at the API boundary.
TEMPERATURE_RANGE = (0.0, 2.0)
TOP_P_RANGE = (0.0, 1.0)  # exclusive lower bound
NUM_CTX_RANGE = (512, 16384)  # above 16k a 14B model spills out of a 12 GB GPU (slow host)

NAME_MAX_CHARS = 60
DESCRIPTION_MAX_CHARS = 200
SYSTEM_PROMPT_MAX_CHARS = 8000
COPY_SUFFIX = " (copia)"


@dataclass(frozen=True, slots=True)
class GenerationParams:
    """Sampling parameters; None means "use the model's default"."""

    temperature: float | None = None
    top_p: float | None = None
    num_ctx: int | None = None


@dataclass(frozen=True, slots=True)
class PersonalityFields:
    """The editable part of a personality."""

    name: str
    icon: str
    description: str
    system_prompt: str
    params: GenerationParams
    default_model: str | None = None


@dataclass(frozen=True, slots=True)
class Personality:
    id: str
    fields: PersonalityFields
    builtin: bool
    created_at: datetime
    updated_at: datetime


def copy_name(name: str) -> str:
    """Name for a duplicate: "<name> (copia)", trimmed to fit."""
    return name[: NAME_MAX_CHARS - len(COPY_SUFFIX)].rstrip() + COPY_SUFFIX
