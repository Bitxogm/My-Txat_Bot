from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.api.dependencies import get_app_settings, get_auth_service, require_session
from app.core.auth import SESSION_COOKIE, SESSION_COOKIE_PATH, AuthService, Session
from app.core.config import Settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    # Bounded so huge payloads can't be used to burn CPU in the hash check.
    password: str = Field(min_length=1, max_length=1024)


class MeResponse(BaseModel):
    username: str


@router.post("/login", status_code=204)
async def login(
    body: LoginRequest,
    response: Response,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> None:
    token = await auth.login(body.username, body.password)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=auth.session_max_age,
        path=SESSION_COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    _session: Annotated[Session, Depends(require_session)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> None:
    auth.logout()
    response.delete_cookie(
        SESSION_COOKIE,
        path=SESSION_COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )


@router.get("/me")
async def me(session: Annotated[Session, Depends(require_session)]) -> MeResponse:
    return MeResponse(username=session.username)
