import asyncio
import hashlib
import hmac
import logging
import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import Settings
from app.core.errors import (
    AuthNotConfiguredError,
    InvalidCredentialsError,
    TooManyLoginAttemptsError,
    UnauthorizedError,
)

logger = logging.getLogger(__name__)

SESSION_COOKIE = "txat_session"
SESSION_COOKIE_PATH = "/api"
_SESSION_SALT = "txat-session"


class LoginRateLimiter:
    """Global sliding window of failed logins.

    Global (not per IP) on purpose: there is a single user and the backend port can be reached
    directly, so a client-supplied X-Forwarded-For could not be trusted to tell clients apart.
    """

    def __init__(
        self, max_failures: int, window_seconds: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: deque[float] = deque()

    def _prune(self, now: float) -> None:
        while self._failures and now - self._failures[0] >= self._window:
            self._failures.popleft()

    def acquire(self) -> None:
        """Reserve one attempt or raise TooManyLoginAttemptsError.

        The attempt counts as a failure up front (no await between the check and the append), so
        concurrent requests cannot all pass before any of them is recorded. reset() on success.
        """
        now = self._clock()
        self._prune(now)
        if len(self._failures) >= self._max:
            retry_after = math.ceil(self._window - (now - self._failures[0]))
            raise TooManyLoginAttemptsError(headers={"Retry-After": str(max(retry_after, 1))})
        self._failures.append(now)

    def reset(self) -> None:
        self._failures.clear()


@dataclass(frozen=True, slots=True)
class Session:
    username: str


def is_valid_password_hash(value: str) -> bool:
    if not value.startswith("$argon2id$"):
        return False
    try:
        extract_parameters(value)
    except InvalidHashError:
        return False
    return True


class AuthService:
    def __init__(
        self,
        settings: Settings,
        limiter: LoginRateLimiter | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._hasher = PasswordHasher()
        self._limiter = limiter or LoginRateLimiter(
            settings.login_max_failures, settings.login_window_seconds
        )
        # One argon2 check at a time: each one takes ~64 MiB and a CPU core.
        self._hash_slot = asyncio.Semaphore(1)
        secret = settings.session_secret.get_secret_value()
        self._serializer = URLSafeTimedSerializer(
            secret, salt=_SESSION_SALT, signer_kwargs={"digest_method": hashlib.sha256}
        )
        # Ties sessions to the current password: changing AUTH_PASSWORD_HASH logs everyone out.
        self._password_fingerprint = hmac.new(
            secret.encode(), settings.auth_password_hash.get_secret_value().encode(), "sha256"
        ).hexdigest()[:32]
        self._clock = clock
        # Tokens issued before this instant are rejected. Logout moves it forward, and starting the
        # process sets it, so a restart also closes every session (there is no session store).
        self._sessions_valid_after = clock()

    @property
    def is_configured(self) -> bool:
        return self._settings.auth_configured and is_valid_password_hash(
            self._settings.auth_password_hash.get_secret_value()
        )

    @property
    def session_max_age(self) -> int:
        return self._settings.session_ttl_hours * 3600

    def _require_configured(self) -> None:
        if not self.is_configured:
            raise AuthNotConfiguredError

    async def login(self, username: str, password: str) -> str:
        """Check credentials and return a signed session token."""
        self._require_configured()
        self._limiter.acquire()

        username_ok = hmac.compare_digest(username.encode(), self._settings.auth_username.encode())
        # Always run the (slow) hash check so a wrong username takes as long as a wrong password.
        async with self._hash_slot:
            password_ok = await asyncio.to_thread(self._verify_password, password)
        if not (username_ok and password_ok):
            logger.warning("Failed login attempt")
            raise InvalidCredentialsError

        self._limiter.reset()
        logger.info("Successful login")
        return self._serializer.dumps(
            {"u": username, "p": self._password_fingerprint, "iat": self._clock()}
        )

    def logout(self) -> None:
        """Invalidate every session issued so far (single user: logout is global)."""
        self._sessions_valid_after = self._clock()
        logger.info("Logout: all sessions closed")

    def _verify_password(self, password: str) -> bool:
        try:
            return self._hasher.verify(
                self._settings.auth_password_hash.get_secret_value(), password
            )
        except VerificationError:
            return False
        except InvalidHashError:
            logger.error("AUTH_PASSWORD_HASH is not a valid argon2 hash")
            return False

    def authenticate(self, token: str | None) -> Session:
        """Return the session for a token or raise UnauthorizedError."""
        self._require_configured()
        if not token:
            raise UnauthorizedError
        try:
            data = self._serializer.loads(token, max_age=self.session_max_age)
        except BadSignature as exc:
            raise UnauthorizedError from exc
        if (
            not isinstance(data, dict)
            or data.get("u") != self._settings.auth_username
            or data.get("p") != self._password_fingerprint
        ):
            raise UnauthorizedError
        issued_at = data.get("iat")
        if not isinstance(issued_at, int | float) or issued_at <= self._sessions_valid_after:
            raise UnauthorizedError
        return Session(username=self._settings.auth_username)
