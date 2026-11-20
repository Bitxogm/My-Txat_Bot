import re
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"

# Client-supplied IDs end up in logs, so only a short, safe charset is accepted.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def resolve_request_id(incoming: str | None) -> str:
    if incoming and _VALID_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


def get_request_id() -> str:
    return request_id_var.get()
