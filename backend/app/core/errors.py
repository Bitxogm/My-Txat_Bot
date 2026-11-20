import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_id import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base domain error. Routes raise these; the global handler renders them."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    message: str = "Error interno del servidor"

    def __init__(self, message: str | None = None, headers: dict[str, str] | None = None) -> None:
        if message is not None:
            self.message = message
        self.headers = headers or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "NOT_FOUND"
    message = "Recurso no encontrado"


class ConversationNotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "CONVERSATION_NOT_FOUND"
    message = "La conversación no existe"


class BadRequestError(AppError):
    status_code = HTTPStatus.BAD_REQUEST
    code = "BAD_REQUEST"
    message = "Petición no válida"


class UnauthorizedError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "UNAUTHORIZED"
    message = "Sesión no válida o caducada. Inicia sesión."


class InvalidCredentialsError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "INVALID_CREDENTIALS"
    message = "Usuario o contraseña incorrectos"


class TooManyLoginAttemptsError(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "TOO_MANY_ATTEMPTS"
    message = "Demasiados intentos fallidos. Espera unos minutos."


class AuthNotConfiguredError(AppError):
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "AUTH_NOT_CONFIGURED"
    message = "El login no está configurado en el servidor"


class ModelUnavailableError(AppError):
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "MODEL_UNAVAILABLE"
    message = "El servidor de modelos no está disponible"


class EmptyReplyError(AppError):
    status_code = HTTPStatus.BAD_GATEWAY
    code = "EMPTY_REPLY"
    message = "El modelo no devolvió ninguna respuesta"


class ModelRateLimitedError(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "MODEL_RATE_LIMITED"
    message = "Se ha alcanzado el límite de uso del proveedor en la nube. Espera un poco."


class ModelNotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "MODEL_NOT_FOUND"
    message = "El modelo no existe en el servidor de modelos"


_HTTP_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "PAYLOAD_TOO_LARGE",
    429: "TOO_MANY_REQUESTS",
}


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    request_id = get_request_id()
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers={REQUEST_ID_HEADER: request_id},
    )


def internal_error_response() -> JSONResponse:
    return error_response(500, AppError.code, AppError.message)


async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error("%s: %s", exc.code, exc.message)
    response = error_response(exc.status_code, exc.code, exc.message)
    response.headers.update(exc.headers)
    return response


async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    if isinstance(exc.detail, str) and exc.detail:
        message = exc.detail
    else:
        message = HTTPStatus(exc.status_code).phrase
    response = error_response(exc.status_code, code, message)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.get("loc", ()))
        message = f"{location}: {first.get('msg', 'valor no válido')}"
    else:
        message = "Datos de entrada no válidos"
    return error_response(422, "VALIDATION_ERROR", message)


def register_exception_handlers(app: FastAPI) -> None:
    # Unhandled exceptions are caught in RequestContextMiddleware, which can still add
    # the request_id header; Starlette's catch-all handler runs outside user middleware.
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
