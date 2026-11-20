from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.errors import ModelUnavailableError


class Payload(BaseModel):
    name: str


@pytest.fixture
def app_with_test_routes(app: FastAPI) -> FastAPI:
    @app.get("/api/_test/app-error")
    async def raise_app_error() -> None:
        raise ModelUnavailableError

    @app.get("/api/_test/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal detail")

    @app.post("/api/_test/validate")
    async def validate(payload: Payload) -> Payload:
        return payload

    return app


@pytest.fixture
def test_client(
    app_with_test_routes: FastAPI, make_client: Callable[[FastAPI], httpx.AsyncClient]
) -> httpx.AsyncClient:
    return make_client(app_with_test_routes)


def assert_error_shape(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


async def test_unknown_route_returns_not_found(test_client: httpx.AsyncClient) -> None:
    async with test_client as c:
        response = await c.get("/api/does-not-exist")

    assert_error_shape(response, 404, "NOT_FOUND")


async def test_app_error_is_rendered(test_client: httpx.AsyncClient) -> None:
    async with test_client as c:
        response = await c.get("/api/_test/app-error")

    assert_error_shape(response, 503, "MODEL_UNAVAILABLE")


async def test_validation_error_is_rendered(test_client: httpx.AsyncClient) -> None:
    async with test_client as c:
        response = await c.post("/api/_test/validate", json={})

    assert_error_shape(response, 422, "VALIDATION_ERROR")
    assert "name" in response.json()["error"]["message"]


async def test_method_not_allowed(test_client: httpx.AsyncClient) -> None:
    async with test_client as c:
        response = await c.delete("/api/health")

    assert_error_shape(response, 405, "METHOD_NOT_ALLOWED")


async def test_unhandled_error_hides_details(test_client: httpx.AsyncClient) -> None:
    async with test_client as c:
        response = await c.get("/api/_test/crash")

    assert_error_shape(response, 500, "INTERNAL_ERROR")
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text
