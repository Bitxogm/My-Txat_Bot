import ipaddress
import re
import unicodedata
from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Path, Query
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from app.api.dependencies import get_osint_source_repository
from app.core.errors import (
    BuiltinOsintSourceError,
    OsintSourceLimitError,
    OsintSourceNotFoundError,
)
from app.domain.osint import (
    DESCRIPTION_MAX_CHARS,
    MAX_CUSTOM_SOURCES,
    NAME_MAX_CHARS,
    URL_MAX_CHARS,
    OsintCategory,
    OsintSource,
    OsintSourceFields,
    has_unsafe_chars,
)
from app.ports.osint_sources import OsintSourceRepository

router = APIRouter(prefix="/osint-sources", tags=["osint-sources"])

# Built-ins use stable slugs, custom sources use uuid4 hex.
SOURCE_ID_PATTERN = r"^(osint-[a-z0-9-]{1,40}|[0-9a-f]{32})$"
SourceId = Annotated[str, Path(pattern=SOURCE_ID_PATTERN)]
Repo = Annotated[OsintSourceRepository, Depends(get_osint_source_repository)]

# These fields end up in the Auditor's system prompt: single line, printable characters only.
_SINGLE_LINE = r"^[^\x00-\x1f\x7f<>`]*$"


def _safe_text(value: str) -> str:
    """NFKC first (so full-width U+FF1C becomes < and is rejected), then no invisible,
    bidi, line-separator, private-use or unassigned characters."""
    normalized = unicodedata.normalize("NFKC", value)
    if has_unsafe_chars(normalized) or re.search(r"[<>`]", normalized):
        raise ValueError("El texto contiene caracteres no permitidos")
    return normalized


Name = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=NAME_MAX_CHARS, pattern=_SINGLE_LINE
    ),
    AfterValidator(_safe_text),
]
Description = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=DESCRIPTION_MAX_CHARS, pattern=_SINGLE_LINE
    ),
    AfterValidator(_safe_text),
]

_URL_FORBIDDEN = set("\"'<>`\\{}|^")
# DNS hostname with a TLD, lower-case (IDN must be entered as punycode, xn--...).
_HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _check_url(value: str) -> str:
    """Absolute http(s) URL to a public DNS name: printable ASCII only (no homographs or
    invisible characters), valid port, no credentials, no IP literals or localhost, and no
    characters that could break out of a link or the prompt block."""
    if not all(0x21 <= ord(ch) <= 0x7E for ch in value) or any(
        ch in _URL_FORBIDDEN for ch in value
    ):
        raise ValueError("La URL solo puede tener caracteres ASCII imprimibles (IDN en punycode)")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("La URL debe empezar por http:// o https:// y tener un dominio")
    if "@" in parts.netloc:
        raise ValueError("La URL no puede llevar usuario ni contraseña")
    try:
        parts.port  # noqa: B018 - raises ValueError on an invalid port
    except ValueError as exc:
        raise ValueError("El puerto de la URL no es válido") from exc
    host = parts.hostname
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Usa un dominio, no una dirección IP")
    if host == "localhost" or host.endswith(".localhost") or not _HOSTNAME.fullmatch(host):
        raise ValueError("El dominio de la URL no es válido")
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


class OsintSourceReplace(OsintSourceIn):
    """PUT is a full replacement: is_active must be sent, so omitting it can't silently
    re-enable a source the user switched off."""

    is_active: bool


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
    if await repo.count_custom() >= MAX_CUSTOM_SOURCES:
        raise OsintSourceLimitError
    return OsintSourceOut.of(await repo.create(body.to_fields(), is_active=body.is_active))


@router.put("/{source_id}")
async def replace_source(
    source_id: SourceId, body: OsintSourceReplace, repo: Repo
) -> OsintSourceOut:
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
    await _require(repo, source_id)
    updated = await repo.toggle(source_id)
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
