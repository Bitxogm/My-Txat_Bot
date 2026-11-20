"""Helpers to fill backend/.env.

uv run python -m app.cli hash-password   # asks for the password, prints AUTH_PASSWORD_HASH
uv run python -m app.cli session-secret  # prints a random SESSION_SECRET
"""

import argparse
import getpass
import secrets
import sys

from argon2 import PasswordHasher

MIN_PASSWORD_LENGTH = 12


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hash-password", help="Genera AUTH_PASSWORD_HASH")
    sub.add_parser("session-secret", help="Genera SESSION_SECRET")
    args = parser.parse_args(argv)
    return hash_password() if args.command == "hash-password" else session_secret()


if __name__ == "__main__":
    raise SystemExit(main())
