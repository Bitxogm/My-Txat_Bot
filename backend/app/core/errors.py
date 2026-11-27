import logging
from http import HTTPStatus
from typing import Any

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

    def __init__(
        self,
        message: str | None = None,
        headers: dict[str, str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        self.headers = headers or {}
        # Extra fields for the error body, next to code/message/request_id. Only for errors the
        # client acts on (e.g. MODEL_RATE_LIMITED: provider and retry_after).
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "NOT_FOUND"
    message = "Recurso no encontrado"


class ConversationNotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "CONVERSATION_NOT_FOUND"
    message = "La conversación no existe"


class PersonalityNotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "PERSONALITY_NOT_FOUND"
    message = "La personalidad no existe"


class BuiltinPersonalityError(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "PERSONALITY_BUILTIN"
    message = (
        "Las personalidades incorporadas no se pueden editar ni borrar."
        " Duplícala para personalizarla."
    )


class OsintSourceNotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "OSINT_SOURCE_NOT_FOUND"
    message = "La fuente OSINT no existe"


class BuiltinOsintSourceError(AppError):
    status_code = HTTPStatus.FORBIDDEN
    code = "OSINT_SOURCE_BUILTIN"
    message = "Las fuentes incorporadas no se pueden editar ni borrar; solo activar o desactivar."


class OsintSourceLimitError(AppError):
    status_code = HTTPStatus.CONFLICT
    code = "OSINT_SOURCE_LIMIT"
    message = "Has llegado al máximo de fuentes propias. Borra o reutiliza alguna."


class UnsupportedMediaTypeError(AppError):
    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    code = "UNSUPPORTED_MEDIA_TYPE"
    message = (
        "Tipo de fichero no admitido. Se aceptan PDF, imágenes (PNG, JPEG, WebP, GIF) y"
        " ficheros de texto (txt, md, log, csv, json, código…)."
    )


class ModelWithoutVisionError(AppError):
    status_code = HTTPStatus.BAD_REQUEST
    code = "MODEL_WITHOUT_VISION"
    message = "Este modelo no admite imágenes. Elige uno con visión o quita las imágenes."


class PayloadTooLargeError(AppError):
    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    code = "PAYLOAD_TOO_LARGE"
    message = "El fichero supera el tamaño máximo permitido"


class LengthRequiredError(AppError):
    status_code = HTTPStatus.LENGTH_REQUIRED
    code = "LENGTH_REQUIRED"
    message = "La subida debe indicar su tamaño (Content-Length)"


class UnreadableFileError(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "UNREADABLE_FILE"
    message = "No se ha podido leer el fichero"


class AttachmentNotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "ATTACHMENT_NOT_FOUND"
    message = "El adjunto no existe en esta conversación"


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


class MessageNotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "MESSAGE_NOT_FOUND"
    message = "El mensaje no existe"


class FeedbackNotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "FEEDBACK_NOT_FOUND"
    message = "Esa respuesta no tiene valoración"


class FeedbackNotAllowedError(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "FEEDBACK_NOT_ALLOWED"
    message = "Solo se pueden valorar respuestas del asistente"


class MemoryNotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    code = "MEMORY_NOT_FOUND"
    message = "Esa memoria no existe"


class MemoryLimitError(AppError):
    status_code = HTTPStatus.CONFLICT
    code = "MEMORY_LIMIT"
    message = "Has llegado al límite de memorias activas"


class PersonalityLockedError(AppError):
    status_code = HTTPStatus.CONFLICT
    code = "PERSONALITY_LOCKED"
    message = "La personalidad se fija al empezar la conversación"


class ContextTooLongError(AppError):
    status_code = HTTPStatus.BAD_REQUEST
    code = "CONTEXT_TOO_LONG"
    message = (
        "El mensaje no cabe en el contexto del modelo. Acórtalo, quita algún fichero o imagen,"
        " o usa una personalidad con más contexto."
    )


class EmptyReplyError(AppError):
    status_code = HTTPStatus.BAD_GATEWAY
    code = "EMPTY_REPLY"
    message = "El modelo no devolvió ninguna respuesta"


class ModelRateLimitedError(AppError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "MODEL_RATE_LIMITED"
    message = "Se ha alcanzado el límite de uso del proveedor en la nube. Espera un poco."

    @classmethod
    def for_provider(cls, provider: str, retry_after: int | None) -> "ModelRateLimitedError":
        """The body carries `provider` and `retry_after` (seconds, or null if unknown) so the
        client can say when it can try again; Retry-After goes as a header too."""
        if retry_after is None:
            message = f"Límite de {provider} alcanzado. Espera un poco antes de reintentar."
        else:
            message = f"Límite de {provider} alcanzado, disponible en {retry_after} s."
        headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
        return cls(
            message, headers=headers, details={"provider": provider, "retry_after": retry_after}
        )


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


def error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    request_id = get_request_id()
    body = {**(details or {}), "code": code, "message": message, "request_id": request_id}
    return JSONResponse(
        status_code=status_code,
        content={"error": body},
        headers={REQUEST_ID_HEADER: request_id},
    )


def internal_error_response() -> JSONResponse:
    return error_response(500, AppError.code, AppError.message)


async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error("%s: %s", exc.code, exc.message)
    response = error_response(exc.status_code, exc.code, exc.message, exc.details)
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
        # "body.url" -> "url": the field name is what the user can act on.
        location = [str(part) for part in first.get("loc", ()) if part not in ("body", "query")]
        detail = str(first.get("msg", "valor no válido")).removeprefix("Value error, ")
        message = f"{'.'.join(location)}: {detail}" if location else detail
    else:
        message = "Datos de entrada no válidos"
    return error_response(422, "VALIDATION_ERROR", message)


def register_exception_handlers(app: FastAPI) -> None:
    # Unhandled exceptions are caught in RequestContextMiddleware, which can still add
    # the request_id header; Starlette's catch-all handler runs outside user middleware.
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
