"""Persistent memory (ADR-025): entries about the user, injected into every conversation."""

import asyncio
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from app.api.dependencies import get_app_settings_repository, get_memory_repository
from app.core.errors import MemoryLimitError, MemoryNotFoundError
from app.domain.memory import (
    ACTIVE_MEMORY_MAX_CHARS,
    MAX_ACTIVE_MEMORIES,
    MAX_MEMORIES,
    MEMORY_MAX_CHARS,
    Memory,
    MemoryCategory,
    normalize_memory_text,
)
from app.ports.memories import AppSettingsRepository, MemoryRepository

router = APIRouter(prefix="/memories", tags=["memories"])

# The default entry from the migration has a fixed slug; the rest are uuid4 hex.
MEMORY_ID_PATTERN = r"^(memory-[a-z0-9-]{1,40}|[0-9a-f]{32})$"
MemoryId = Annotated[str, Path(pattern=MEMORY_ID_PATTERN)]
Repo = Annotated[MemoryRepository, Depends(get_memory_repository)]
SettingsRepo = Annotated[AppSettingsRepository, Depends(get_app_settings_repository)]

# The length is checked again after NFKC in normalize_memory_text; this first bound only
# keeps oversized bodies from being normalized at all.
MemoryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MEMORY_MAX_CHARS),
    AfterValidator(normalize_memory_text),
]

# Checking the limits and writing are separate awaits: two concurrent requests could both pass.
_write_lock = asyncio.Lock()


class MemoryIn(BaseModel):
    """POST creates and PUT replaces the whole entry (is_active included)."""

    model_config = ConfigDict(extra="forbid")

    category: MemoryCategory
    text: MemoryText
    is_active: bool = True


class MemoryReplace(MemoryIn):
    is_active: bool


class MemoryOut(BaseModel):
    id: str
    category: MemoryCategory
    text: str
    is_active: bool
    # Set for "in progress" entries archived after two weeks without edits; editing or
    # reactivating one takes it out.
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, m: Memory) -> "MemoryOut":
        return cls(
            id=m.id,
            category=m.category,
            text=m.text,
            is_active=m.is_active,
            archived_at=m.archived_at,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class MemoryLimits(BaseModel):
    max_active: int = MAX_ACTIVE_MEMORIES
    max_chars: int = MEMORY_MAX_CHARS
    max_active_chars: int = ACTIVE_MEMORY_MAX_CHARS


class MemoryList(BaseModel):
    memories: list[MemoryOut]
    limits: MemoryLimits
    send_to_remote: bool


class MemorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    send_to_remote: bool


def _now() -> datetime:
    return datetime.now(UTC)


async def _check_limits(repo: MemoryRepository, replacing: str | None, entry: MemoryIn) -> None:
    """The entries in use after this change must stay within the count and size limits."""
    if not entry.is_active:
        return
    others = [m for m in await repo.in_use(_now()) if m.id != replacing]
    if len(others) + 1 > MAX_ACTIVE_MEMORIES:
        raise MemoryLimitError(
            f"Como mucho {MAX_ACTIVE_MEMORIES} memorias activas: desactiva o borra alguna"
        )
    if sum(len(m.text) for m in others) + len(entry.text) > ACTIVE_MEMORY_MAX_CHARS:
        raise MemoryLimitError(
            f"Las memorias activas no pueden pasar de {ACTIVE_MEMORY_MAX_CHARS} caracteres"
            " en total: acorta o desactiva alguna"
        )


@router.get("")
async def list_memories(repo: Repo, settings: SettingsRepo) -> MemoryList:
    return MemoryList(
        memories=[MemoryOut.of(m) for m in await repo.list_all(_now())],
        limits=MemoryLimits(),
        send_to_remote=await settings.memory_to_remote(),
    )


@router.put("/settings")
async def update_settings(body: MemorySettings, settings: SettingsRepo) -> MemorySettings:
    await settings.set_memory_to_remote(body.send_to_remote)
    return MemorySettings(send_to_remote=await settings.memory_to_remote())


@router.post("", status_code=201)
async def create_memory(body: MemoryIn, repo: Repo) -> MemoryOut:
    async with _write_lock:
        if len(await repo.list_all(_now())) >= MAX_MEMORIES:
            raise MemoryLimitError(
                f"Como mucho {MAX_MEMORIES} memorias en total: borra alguna desactivada o archivada"
            )
        await _check_limits(repo, None, body)
        return MemoryOut.of(await repo.create(body.category, body.text, body.is_active))


@router.put("/{memory_id}")
async def replace_memory(memory_id: MemoryId, body: MemoryReplace, repo: Repo) -> MemoryOut:
    async with _write_lock:
        if await repo.get(memory_id) is None:
            raise MemoryNotFoundError
        await _check_limits(repo, memory_id, body)
        updated = await repo.replace(memory_id, body.category, body.text, body.is_active)
    if updated is None:
        raise MemoryNotFoundError
    return MemoryOut.of(updated)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: MemoryId, repo: Repo) -> None:
    if not await repo.delete(memory_id):
        raise MemoryNotFoundError
