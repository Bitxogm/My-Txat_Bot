import re

import httpx
import pytest

from app.core.request_id import resolve_request_id


async def test_generates_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


async def test_echoes_valid_incoming_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health", headers={"X-Request-ID": "abc-123.DEF_4"})

    assert response.headers["X-Request-ID"] == "abc-123.DEF_4"


@pytest.mark.parametrize("bad", ["", "with space", "x" * 129, "line\nbreak", "ñ"])
def test_rejects_unsafe_request_id(bad: str) -> None:
    assert resolve_request_id(bad) != bad
