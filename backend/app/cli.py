"""Helpers to fill backend/.env.

uv run python -m app.cli hash-password   # asks for the password, prints AUTH_PASSWORD_HASH
uv run python -m app.cli session-secret  # prints a random SESSION_SECRET
uv run python -m app.cli dev-login       # local dev only: random password + quick-login card
"""

import argparse
import getpass
import os
import re
import secrets
import shutil
import sys
from pathlib import Path

from argon2 import PasswordHasher

MIN_PASSWORD_LENGTH = 12
MIN_SESSION_SECRET_LENGTH = 32
REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_USERNAME = "void"


def hash_password() -> int:
    password = getpass.getpass("Contraseña: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.stderr.write(f"Usa al menos {MIN_PASSWORD_LENGTH} caracteres.\n")
        return 1
    if getpass.getpass("Repite la contraseña: ") != password:
        sys.stderr.write("Las contraseñas no coinciden.\n")
        return 1
    # Single quotes keep the "$" in the hash literal when Compose reads the .env file.
    sys.stdout.write(f"AUTH_PASSWORD_HASH='{PasswordHasher().hash(password)}'\n")
    return 0


def session_secret() -> int:
    sys.stdout.write(f"SESSION_SECRET={secrets.token_urlsafe(48)}\n")
    return 0


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.lstrip().startswith("#"):
                values[key.strip()] = value.strip().strip("'\"")
    return values


def _set_env(path: Path, updates: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    for key, value in updates.items():
        line = f"{key}={value}"
        text, count = re.subn(
            rf"^{re.escape(key)}=.*$", lambda _m, line=line: line, text, flags=re.M
        )
        if count == 0:
            text += ("" if text.endswith("\n") or not text else "\n") + line + "\n"
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def dev_login(root: Path = REPO_ROOT) -> int:
    """Create throwaway local credentials and the quick-login card values.

    Writes the password hash to backend/.env and the plain password to frontend/.env.local
    (both git-ignored). The card only exists in `npm run dev`; production builds drop it.
    Never use this on an instance reachable by other people: run hash-password instead.
    """
    backend_env = root / "backend" / ".env"
    if not backend_env.exists():
        shutil.copyfile(root / "backend" / ".env.example", backend_env)

    current = _read_env(backend_env)
    username = current.get("AUTH_USERNAME") or DEV_USERNAME
    password = secrets.token_urlsafe(18)
    updates = {
        "AUTH_USERNAME": username,
        "AUTH_PASSWORD_HASH": f"'{PasswordHasher().hash(password)}'",
    }
    if len(current.get("SESSION_SECRET", "")) < MIN_SESSION_SECRET_LENGTH:
        updates["SESSION_SECRET"] = secrets.token_urlsafe(48)
    _set_env(backend_env, updates)
    _set_env(
        root / "frontend" / ".env.local",
        {"VITE_DEV_LOGIN_USER": username, "VITE_DEV_LOGIN_PASSWORD": password},
    )
    sys.stdout.write(
        f"Credenciales de desarrollo listas para '{username}'.\n"
        "Reinicia el backend y recarga el frontend: la tarjeta de acceso rápido las rellena.\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hash-password", help="Genera AUTH_PASSWORD_HASH")
    sub.add_parser("session-secret", help="Genera SESSION_SECRET")
    sub.add_parser("dev-login", help="Credenciales locales de desarrollo + tarjeta de acceso")
    args = parser.parse_args(argv)
    commands = {
        "hash-password": hash_password,
        "session-secret": session_secret,
        "dev-login": dev_login,
    }
    return commands[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
