"""Helpers to fill backend/.env.

uv run python -m app.cli hash-password   # asks for the password, prints AUTH_PASSWORD_HASH
uv run python -m app.cli session-secret  # prints a random SESSION_SECRET
uv run python -m app.cli dev-login       # local dev only: random password + quick-login card
uv run python -m app.cli eval --models qwen3.5:9b groq/openai/gpt-oss-120b [--think on|off]
                                         # answer battery (evals/questions.yaml) -> evals/reports/
"""

import argparse
import getpass
import os
import re
import secrets
import sys
import tempfile
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


_ENV_LINE = r"^\s*(?:export\s+)?{key}\s*="
_SAFE_USERNAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
DEV_LOGIN_MARKER = "DEV_LOGIN"


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            key = key.strip().removeprefix("export ").strip()
            if sep and not key.startswith("#"):
                values[key] = value.strip().strip("'\"")
    return values


def _write_private(path: Path, text: str) -> None:
    """Atomic write with 0600 from the start; replaces a symlink instead of following it."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _set_env(path: Path, updates: dict[str, str], base: str | None = None) -> None:
    if base is not None:
        text = base
    else:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
    for key, value in updates.items():
        line = f"{key}={value}"
        text, count = re.subn(
            _ENV_LINE.format(key=re.escape(key)) + ".*$",
            lambda _m, line=line: line,
            text,
            flags=re.M,
        )
        if count == 0:
            text += ("" if text.endswith("\n") or not text else "\n") + line + "\n"
    _write_private(path, text)


def dev_login(root: Path = REPO_ROOT, force: bool = False) -> int:
    """Create throwaway local credentials and the quick-login card values.

    Writes the password hash to backend/.env (marked with DEV_LOGIN=1) and the plain password
    to frontend/.env.local, both git-ignored and 0600. The card only exists in `npm run dev`;
    production builds drop it. Refuses with APP_ENV=production, and refuses to replace a
    password not created by dev-login unless `force` is set.
    """
    backend_env = root / "backend" / ".env"
    base = None
    if not backend_env.exists():
        base = (root / "backend" / ".env.example").read_text(encoding="utf-8")

    current = _read_env(backend_env)
    if current.get("APP_ENV") == "production":
        sys.stderr.write("dev-login no se usa con APP_ENV=production. Usa hash-password.\n")
        return 1
    if current.get("AUTH_PASSWORD_HASH") and current.get(DEV_LOGIN_MARKER) != "1" and not force:
        sys.stderr.write(
            "backend/.env ya tiene una contraseña que no creó dev-login (es la que usa"
            " docker compose). No la sustituyo; usa --force si de verdad quieres.\n"
        )
        return 1

    username = current.get("AUTH_USERNAME") or DEV_USERNAME
    if not _SAFE_USERNAME.fullmatch(username):
        sys.stderr.write("AUTH_USERNAME solo puede tener letras, números, '.', '_' y '-'.\n")
        return 1

    password = secrets.token_urlsafe(18)
    updates = {
        "AUTH_USERNAME": username,
        "AUTH_PASSWORD_HASH": f"'{PasswordHasher().hash(password)}'",
        DEV_LOGIN_MARKER: "1",
    }
    if len(current.get("SESSION_SECRET", "")) < MIN_SESSION_SECRET_LENGTH:
        updates["SESSION_SECRET"] = secrets.token_urlsafe(48)
    _set_env(backend_env, updates, base=base)
    _set_env(
        root / "frontend" / ".env.local",
        {"DEV_LOGIN_USER": username, "DEV_LOGIN_PASSWORD": password},
    )
    sys.stdout.write(
        f"Credenciales de desarrollo listas para '{username}'.\n"
        "Reinicia el backend y recarga el frontend: la tarjeta de acceso rápido las rellena.\n"
    )
    return 0


EVALS_DIR = REPO_ROOT / "evals"


def run_evals(
    models: list[str],
    think: str | None,
    personality: str | None,
    questions_file: Path,
    out_dir: Path,
    only: list[str] | None,
) -> int:
    """Asks every question to every model and writes one Markdown report per model."""
    import asyncio
    from datetime import datetime

    from app.adapters.llm_factory import build_llm_provider
    from app.core.config import get_settings
    from app.evals.checks import load_questions
    from app.evals.runner import (
        Result,
        ask,
        render_report,
        report_path,
        resolve_personality,
    )

    try:
        questions = load_questions(questions_file)
        if personality:
            resolve_personality(personality)
        for q in questions:
            if q.personality:
                resolve_personality(q.personality)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    if only:
        questions = [q for q in questions if q.id in only]
    think_flag = None if think is None else think == "on"
    settings = get_settings()

    async def run() -> list[tuple[str, bool | None, list[Result]]]:
        llm, clients = build_llm_provider(settings, think=think_flag)
        runs: list[tuple[str, bool | None, list[Result]]] = []
        try:
            for model in models:
                remote = settings.cloud_enabled and model.startswith(f"{settings.cloud_name}/")
                model_think = (
                    None
                    if remote
                    else (settings.ollama_think if think_flag is None else think_flag)
                )
                results: list[Result] = []
                for q in questions:
                    result = await ask(llm, model, q, personality, settings)
                    sys.stdout.write(
                        f"{model} · {q.id}: {result.status} ({result.seconds:.1f} s)\n"
                    )
                    sys.stdout.flush()
                    results.append(result)
                runs.append((model, model_think, results))
        finally:
            for client in clients:
                await client.aclose()
        return runs

    runs = asyncio.run(run())
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    for model, model_think, results in runs:
        path = report_path(out_dir, model, model_think, now)
        path.write_text(render_report(model, model_think, results, now), encoding="utf-8")
        passed = sum(1 for r in results if r.status != "FALLO")
        sys.stdout.write(f"{model}: {passed}/{len(results)} · informe en {path}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hash-password", help="Genera AUTH_PASSWORD_HASH")
    sub.add_parser("session-secret", help="Genera SESSION_SECRET")
    dev = sub.add_parser("dev-login", help="Credenciales locales de desarrollo + tarjeta de acceso")
    dev.add_argument("--force", action="store_true", help="Sustituir una contraseña existente")
    ev = sub.add_parser("eval", help="Batería de evaluación de respuestas (evals/questions.yaml)")
    ev.add_argument("--models", nargs="+", required=True, help="Modelos, p. ej. qwen3.5:9b")
    ev.add_argument("--think", choices=["on", "off"], help="Razonamiento de Ollama (def.: .env)")
    ev.add_argument(
        "--personality", help="Personalidad por defecto (id o nombre; def.: Mentor CTF)"
    )
    ev.add_argument("--questions", type=Path, default=EVALS_DIR / "questions.yaml")
    ev.add_argument("--out", type=Path, default=EVALS_DIR / "reports")
    ev.add_argument("--only", nargs="+", help="Solo estos ids de pregunta")
    args = parser.parse_args(argv)
    if args.command == "eval":
        return run_evals(
            args.models, args.think, args.personality, args.questions, args.out, args.only
        )
    if args.command == "hash-password":
        return hash_password()
    if args.command == "session-secret":
        return session_secret()
    return dev_login(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
