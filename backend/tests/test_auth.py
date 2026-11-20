import asyncio
import hashlib
from collections.abc import Callable

import httpx
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from itsdangerous import TimestampSigner, URLSafeTimedSerializer

from app.api.dependencies import get_llm_provider
from app.core.auth import SESSION_COOKIE, LoginRateLimiter
from app.core.errors import TooManyLoginAttemptsError
from app.main import create_app
from tests.conftest import (
    TEST_PASSWORD,
    TEST_SESSION_SECRET,
    TEST_USERNAME,
    FakeLLMProvider,
    log_in,
    make_settings,
)

GOOD = {"username": TEST_USERNAME, "password": TEST_PASSWORD}
BAD = {"username": TEST_USERNAME, "password": "nope"}
SHA256 = {"digest_method": hashlib.sha256}


def error_code(response: httpx.Response) -> str:
    return str(response.json()["error"]["code"])


async def test_login_sets_hardened_session_cookie(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.post("/api/auth/login", json=GOOD)

    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api" in cookie
    assert "max-age=259200" in cookie
    assert "secure" not in cookie


async def test_secure_flag_when_configured(
    fake_llm: FakeLLMProvider, make_client: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    app = create_app(make_settings(cookie_secure=True))
    async with make_client(app) as c:
        response = await c.post("/api/auth/login", json=GOOD)

    assert "secure" in response.headers["set-cookie"].lower()


@pytest.mark.parametrize(
    "body",
    [
        {"username": TEST_USERNAME, "password": "wrong password"},
        {"username": "someone-else", "password": TEST_PASSWORD},
    ],
)
async def test_wrong_credentials_give_the_same_error(
    anon_client: httpx.AsyncClient, body: dict[str, str]
) -> None:
    response = await anon_client.post("/api/auth/login", json=body)

    assert response.status_code == 401
    assert error_code(response) == "INVALID_CREDENTIALS"
    assert "set-cookie" not in response.headers


async def test_me_requires_a_session(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/auth/me")

    assert response.status_code == 401
    assert error_code(response) == "UNAUTHORIZED"


async def test_me_returns_the_user(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me")

    assert response.json() == {"username": TEST_USERNAME}


@pytest.mark.parametrize(("method", "path"), [("GET", "/api/models"), ("POST", "/api/chat")])
async def test_protected_routes_reject_anonymous(
    anon_client: httpx.AsyncClient, fake_llm: FakeLLMProvider, method: str, path: str
) -> None:
    response = await anon_client.request(
        method, path, json={"model": "m", "messages": [{"role": "user", "content": "x"}]}
    )

    assert response.status_code == 401
    assert fake_llm.calls == []


async def test_health_stays_public(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.get("/api/health")).status_code == 200


async def test_logout_clears_the_cookie(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert f'{SESSION_COOKIE}=""' in response.headers["set-cookie"]
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_rejects_tampered_or_foreign_tokens(anon_client: httpx.AsyncClient) -> None:
    foreign = URLSafeTimedSerializer("x" * 48, salt="txat-session", signer_kwargs=SHA256).dumps(
        {"u": TEST_USERNAME, "p": "whatever"}
    )
    for token in ["garbage", foreign]:
        anon_client.cookies.set(SESSION_COOKIE, token)
        assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_password_change_invalidates_sessions(
    make_client: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    old_app = create_app(make_settings())
    async with make_client(old_app) as c:
        await log_in(c)
        token = c.cookies[SESSION_COOKIE]

    new_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("another password")
    new_app = create_app(make_settings(auth_password_hash=new_hash))
    async with make_client(new_app) as c:
        c.cookies.set(SESSION_COOKIE, token)
        assert (await c.get("/api/auth/me")).status_code == 401


async def test_expired_session_is_rejected(
    make_client: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    signer = URLSafeTimedSerializer(TEST_SESSION_SECRET, salt="txat-session", signer_kwargs=SHA256)
    app = create_app(make_settings(session_ttl_hours=1))
    async with make_client(app) as c:
        await log_in(c)
        payload = signer.loads(c.cookies[SESSION_COOKIE])

    class TwoHoursAgo(TimestampSigner):
        def get_timestamp(self) -> int:
            return super().get_timestamp() - 2 * 3600

    stale = URLSafeTimedSerializer(
        TEST_SESSION_SECRET, salt="txat-session", signer=TwoHoursAgo, signer_kwargs=SHA256
    ).dumps(payload)
    async with make_client(app) as c:
        c.cookies.set(SESSION_COOKIE, stale)
        assert (await c.get("/api/auth/me")).status_code == 401


async def test_locks_out_after_repeated_failures(
    fake_llm: FakeLLMProvider, make_client: Callable[[FastAPI], httpx.AsyncClient]
) -> None:
    app = create_app(make_settings(login_max_failures=3, login_window_seconds=60))
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm
    async with make_client(app) as c:
        for _ in range(3):
            assert (await c.post("/api/auth/login", json=BAD)).status_code == 401
        blocked = await c.post("/api/auth/login", json=GOOD)

    assert blocked.status_code == 429
    assert error_code(blocked) == "TOO_MANY_ATTEMPTS"
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60


@pytest.mark.parametrize(
    "overrides",
    [
        {"auth_username": ""},
        {"auth_password_hash": ""},
        {"session_secret": "too-short"},
        # What Compose leaves of an unquoted hash after expanding "$v", "$m"...
        {"auth_password_hash": "=19=65536,t=3,p=4"},
        {"auth_password_hash": "$2b$12$notargon2notargon2notargon2notargon2notargon2notar"},
    ],
)
async def test_fails_closed_when_not_configured(
    make_client: Callable[[FastAPI], httpx.AsyncClient], overrides: dict[str, str]
) -> None:
    app = create_app(make_settings(**overrides))
    async with make_client(app) as c:
        login = await c.post("/api/auth/login", json=GOOD)
        models = await c.get("/api/models")

    assert login.status_code == 503
    assert error_code(login) == "AUTH_NOT_CONFIGURED"
    assert models.status_code == 503


async def test_rejects_oversized_password(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.post(
        "/api/auth/login", json={"username": TEST_USERNAME, "password": "x" * 1025}
    )

    assert response.status_code == 422


def test_rate_limiter_window_slides() -> None:
    now = [0.0]
    limiter = LoginRateLimiter(max_failures=2, window_seconds=10, clock=lambda: now[0])
    limiter.acquire()
    limiter.acquire()

    with pytest.raises(TooManyLoginAttemptsError) as exc:
        limiter.acquire()
    assert exc.value.headers["Retry-After"] == "10"

    now[0] = 10.0
    limiter.acquire()


async def test_concurrent_attempts_cannot_bypass_the_limit(
    make_client: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    app = create_app(make_settings(login_max_failures=3, login_window_seconds=60))
    async with make_client(app) as c:
        responses = await asyncio.gather(*(c.post("/api/auth/login", json=BAD) for _ in range(20)))

    statuses = sorted(r.status_code for r in responses)
    assert statuses.count(401) == 3
    assert statuses.count(429) == 17


async def test_success_resets_the_failure_count(
    make_client: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    app = create_app(make_settings(login_max_failures=2, login_window_seconds=60))
    async with make_client(app) as c:
        assert (await c.post("/api/auth/login", json=BAD)).status_code == 401
        assert (await c.post("/api/auth/login", json=GOOD)).status_code == 204
        assert (await c.post("/api/auth/login", json=BAD)).status_code == 401
        assert (await c.post("/api/auth/login", json=GOOD)).status_code == 204


async def test_logout_revokes_copied_tokens(client: httpx.AsyncClient) -> None:
    copied = client.cookies[SESSION_COOKIE]

    assert (await client.post("/api/auth/logout")).status_code == 204

    client.cookies.set(SESSION_COOKIE, copied)
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_requires_a_session(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.post("/api/auth/logout")).status_code == 401


async def test_restart_closes_existing_sessions(
    make_client: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    async with make_client(create_app(make_settings())) as c:
        await log_in(c)
        token = c.cookies[SESSION_COOKIE]

    async with make_client(create_app(make_settings())) as c:
        c.cookies.set(SESSION_COOKIE, token)
        assert (await c.get("/api/auth/me")).status_code == 401
