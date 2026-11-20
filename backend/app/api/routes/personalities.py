from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.dependencies import get_personality_repository
from app.core.errors import BuiltinPersonalityError, PersonalityNotFoundError
from app.domain.personality import (
    DESCRIPTION_MAX_CHARS,
    NAME_MAX_CHARS,
    NUM_CTX_RANGE,
    SYSTEM_PROMPT_MAX_CHARS,
    TEMPERATURE_RANGE,
    TOP_P_RANGE,
    GenerationParams,
    Personality,
    PersonalityFields,
    copy_name,
)
from app.ports.personalities import PersonalityRepository

router = APIRouter(prefix="/personalities", tags=["personalities"])

# Built-ins use stable slugs, copies use uuid4 hex.
PERSONALITY_ID_PATTERN = r"^(builtin-[a-z0-9-]{1,40}|[0-9a-f]{32})$"
PersonalityId = Annotated[str, Path(pattern=PERSONALITY_ID_PATTERN)]
Repo = Annotated[PersonalityRepository, Depends(get_personality_repository)]

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_CHARS)
]
# A lucide icon name; the frontend maps known names and falls back to a default icon.
Icon = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,40}$")]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX_CHARS)
]
SystemPrompt = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=SYSTEM_PROMPT_MAX_CHARS),
]
Temperature = Annotated[float, Field(ge=TEMPERATURE_RANGE[0], le=TEMPERATURE_RANGE[1])]
TopP = Annotated[float, Field(gt=TOP_P_RANGE[0], le=TOP_P_RANGE[1])]
NumCtx = Annotated[int, Field(ge=NUM_CTX_RANGE[0], le=NUM_CTX_RANGE[1])]
ModelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PersonalityIn(BaseModel):
    # No `builtin` field and extra="forbid": a client can never create or flag a built-in.
    model_config = ConfigDict(extra="forbid")

    name: Name
    icon: Icon = "bot"
    description: Description = ""
    system_prompt: SystemPrompt
    temperature: Temperature | None = None
    top_p: TopP | None = None
    num_ctx: NumCtx | None = None
    default_model: ModelName | None = None

    def to_fields(self) -> PersonalityFields:
        return PersonalityFields(
            name=self.name,
            icon=self.icon,
            description=self.description,
            system_prompt=self.system_prompt,
            params=GenerationParams(
                temperature=self.temperature, top_p=self.top_p, num_ctx=self.num_ctx
            ),
            default_model=self.default_model,
        )


class PersonalityPatch(BaseModel):
    """Partial update: only the fields sent change; sending null clears a nullable field."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    icon: Icon | None = None
    description: Description | None = None
    system_prompt: SystemPrompt | None = None
    temperature: Temperature | None = None
    top_p: TopP | None = None
    num_ctx: NumCtx | None = None
    default_model: ModelName | None = None

    def apply(self, current: PersonalityFields) -> PersonalityFields:
        sent = self.model_fields_set

        def pick[T](name: str, value: T, old: T) -> T:
            return value if name in sent else old

        params = current.params
        return PersonalityFields(
            # Required text fields can't be cleared: null keeps the current value.
            name=self.name if self.name is not None else current.name,
            icon=self.icon if self.icon is not None else current.icon,
            description=(self.description if self.description is not None else current.description),
            system_prompt=(
                self.system_prompt if self.system_prompt is not None else current.system_prompt
            ),
            params=GenerationParams(
                temperature=pick("temperature", self.temperature, params.temperature),
                top_p=pick("top_p", self.top_p, params.top_p),
                num_ctx=pick("num_ctx", self.num_ctx, params.num_ctx),
            ),
            default_model=pick("default_model", self.default_model, current.default_model),
        )


class PersonalityOut(BaseModel):
    id: str
    name: str
    icon: str
    description: str
    system_prompt: str
    temperature: float | None
    top_p: float | None
    num_ctx: int | None
    default_model: str | None
    builtin: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, p: Personality) -> "PersonalityOut":
        f = p.fields
        return cls(
            id=p.id,
            name=f.name,
            icon=f.icon,
            description=f.description,
            system_prompt=f.system_prompt,
            temperature=f.params.temperature,
            top_p=f.params.top_p,
            num_ctx=f.params.num_ctx,
            default_model=f.default_model,
            builtin=p.builtin,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )


class PersonalityList(BaseModel):
    personalities: list[PersonalityOut]


async def _require(repo: PersonalityRepository, personality_id: str) -> Personality:
    personality = await repo.get(personality_id)
    if personality is None:
        raise PersonalityNotFoundError
    return personality


async def _require_editable(repo: PersonalityRepository, personality_id: str) -> Personality:
    personality = await _require(repo, personality_id)  # 404 before 403
    if personality.builtin:
        raise BuiltinPersonalityError
    return personality


@router.get("")
async def list_personalities(repo: Repo) -> PersonalityList:
    return PersonalityList(personalities=[PersonalityOut.of(p) for p in await repo.list_all()])


@router.get("/{personality_id}")
async def get_personality(personality_id: PersonalityId, repo: Repo) -> PersonalityOut:
    return PersonalityOut.of(await _require(repo, personality_id))


@router.post("", status_code=201)
async def create_personality(body: PersonalityIn, repo: Repo) -> PersonalityOut:
    return PersonalityOut.of(await repo.create(body.to_fields()))


@router.patch("/{personality_id}")
async def update_personality(
    personality_id: PersonalityId, body: PersonalityPatch, repo: Repo
) -> PersonalityOut:
    current = await _require_editable(repo, personality_id)
    updated = await repo.update(personality_id, body.apply(current.fields))
    if updated is None:  # deleted or protected in between
        raise PersonalityNotFoundError
    return PersonalityOut.of(updated)


@router.delete("/{personality_id}", status_code=204)
async def delete_personality(personality_id: PersonalityId, repo: Repo) -> None:
    await _require_editable(repo, personality_id)
    if not await repo.delete(personality_id):
        raise PersonalityNotFoundError


@router.post("/{personality_id}/duplicate", status_code=201)
async def duplicate_personality(personality_id: PersonalityId, repo: Repo) -> PersonalityOut:
    source = await _require(repo, personality_id)
    fields = source.fields
    copy = PersonalityFields(
        name=copy_name(fields.name),
        icon=fields.icon,
        description=fields.description,
        system_prompt=fields.system_prompt,
        params=fields.params,
        default_model=fields.default_model,
    )
    return PersonalityOut.of(await repo.create(copy))
