from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Path, Query
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from app.api.dependencies import get_osint_source_repository
from app.core.errors import BuiltinOsintSourceError, OsintSourceNotFoundError
from app.domain.osint import (
    DESCRIPTION_MAX_CHARS,
    NAME_MAX_CHARS,
    URL_MAX_CHARS,
    OsintCategory,
    OsintSource,
    OsintSourceFields,
)
from app.ports.osint_sources import OsintSourceRepository

router = APIRouter(prefix="/osint-sources", tags=["osint-sources"])

# Built-ins use stable slugs, custom sources use uuid4 hex.
SOURCE_ID_PATTERN = r"^(osint-[a-z0-9-]{1,40}|[0-9a-f]{32})$"
SourceId = Annotated[str, Path(pattern=SOURCE_ID_PATTERN)]
Repo = Annotated[OsintSourceRepository, Depends(get_osint_source_repository)]

# These fields end up in the Auditor's system prompt: single line, printable characters only.
_SINGLE_LINE = r"^[^\x00-\x1f\x7f<>`]*$"
Name = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=NAME_MAX_CHARS, pattern=_SINGLE_LINE
    ),
]
Description = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=DESCRIPTION_MAX_CHARS, pattern=_SINGLE_LINE
    ),
]

_URL_FORBIDDEN = set(" \t\r\n\"'<>`\\{}|^")


def _check_url(value: str) -> str:
    """Absolute http(s) URL with a host, no credentials and no characters that could break out
    of a link or the prompt block."""
    if any(ch in _URL_FORBIDDEN or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ValueError("La URL contiene caracteres no permitidos")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("La URL debe empezar por http:// o https:// y tener un dominio")
    if "@" in parts.netloc:
        raise ValueError("La URL no puede llevar usuario ni contraseña")
    return value


Url = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=URL_MAX_CHARS),
    AfterValidator(_check_url),
]


class OsintSourceIn(BaseModel):
    # No `builtin` and extra="forbid": a client can never create or flag a built-in.
    model_config = ConfigDict(extra="forbid")

    name: Name
    url: Url
    category: OsintCategory
    description: Description = ""
    requires_api_key: bool = False
    requires_payment: bool = False
    is_active: bool = True

    def to_fields(self) -> OsintSourceFields:
        return OsintSourceFields(
            name=self.name,
            url=self.url,
            category=self.category,
            description=self.description,
            requires_api_key=self.requires_api_key,
            requires_payment=self.requires_payment,
        )


class OsintSourceOut(BaseModel):
    id: str
    name: str
    url: str
    category: OsintCategory
    description: str
    requires_api_key: bool
    requires_payment: bool
    builtin: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, s: OsintSource) -> "OsintSourceOut":
        f = s.fields
        return cls(
            id=s.id,
            name=f.name,
            url=f.url,
            category=f.category,
            description=f.description,
            requires_api_key=f.requires_api_key,
            requires_payment=f.requires_payment,
            builtin=s.builtin,
            is_active=s.is_active,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )


class OsintSourceList(BaseModel):
    sources: list[OsintSourceOut]


async def _require(repo: OsintSourceRepository, source_id: str) -> OsintSource:
    source = await repo.get(source_id)
    if source is None:
        raise OsintSourceNotFoundError
    return source


@router.get("")
async def list_sources(
    repo: Repo, category: Annotated[OsintCategory | None, Query()] = None
) -> OsintSourceList:
    return OsintSourceList(sources=[OsintSourceOut.of(s) for s in await repo.list_all(category)])


@router.post("", status_code=201)
async def create_source(body: OsintSourceIn, repo: Repo) -> OsintSourceOut:
    return OsintSourceOut.of(await repo.create(body.to_fields(), is_active=body.is_active))


@router.put("/{source_id}")
async def replace_source(source_id: SourceId, body: OsintSourceIn, repo: Repo) -> OsintSourceOut:
    """Full update for custom sources. On a built-in only `is_active` may change: any other
    field that differs from the stored value is a 403."""
    current = await _require(repo, source_id)  # 404 before 403
    fields = body.to_fields()
    if current.builtin:
        if fields != current.fields:
            raise BuiltinOsintSourceError
        updated = await repo.set_active(source_id, body.is_active)
    else:
        updated = await repo.update(source_id, fields, body.is_active)
    if updated is None:  # deleted in between
        raise OsintSourceNotFoundError
    return OsintSourceOut.of(updated)


@router.post("/{source_id}/toggle")
async def toggle_source(source_id: SourceId, repo: Repo) -> OsintSourceOut:
    current = await _require(repo, source_id)
    updated = await repo.set_active(source_id, not current.is_active)
    if updated is None:
        raise OsintSourceNotFoundError
    return OsintSourceOut.of(updated)


@router.delete("/{source_id}", status_code=204)
async def delete_source(source_id: SourceId, repo: Repo) -> None:
    current = await _require(repo, source_id)
    if current.builtin:
        raise BuiltinOsintSourceError
    if not await repo.delete(source_id):
        raise OsintSourceNotFoundError
