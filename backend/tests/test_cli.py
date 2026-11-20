from pathlib import Path

import pytest
from argon2 import PasswordHasher

from app import cli


def test_hash_password_prints_a_verifiable_quoted_hash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "a long enough password")

    assert cli.main(["hash-password"]) == 0

    line = capsys.readouterr().out.strip()
    assert line.startswith("AUTH_PASSWORD_HASH='$argon2id$")
    assert PasswordHasher().verify(line.split("'")[1], "a long enough password")


def test_hash_password_rejects_short_passwords(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "short")

    assert cli.main(["hash-password"]) == 1


def test_session_secret_is_long_enough(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["session-secret"]) == 0

    assert len(capsys.readouterr().out.strip().split("=", 1)[1]) >= 32


def _fake_repo(tmp_path: Path, backend_env: str | None = None) -> Path:
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend" / ".env.example").write_text(
        "AUTH_USERNAME=\nAUTH_PASSWORD_HASH=\nSESSION_SECRET=\nOTHER=keep\n"
    )
    if backend_env is not None:
        (tmp_path / "backend" / ".env").write_text(backend_env)
    return tmp_path


def test_dev_login_writes_matching_credentials(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)

    assert cli.dev_login(root) == 0

    backend = cli._read_env(root / "backend" / ".env")
    frontend = cli._read_env(root / "frontend" / ".env.local")
    assert backend["AUTH_USERNAME"] == frontend["VITE_DEV_LOGIN_USER"] == "void"
    assert PasswordHasher().verify(
        backend["AUTH_PASSWORD_HASH"], frontend["VITE_DEV_LOGIN_PASSWORD"]
    )
    assert len(backend["SESSION_SECRET"]) >= 32
    assert backend["OTHER"] == "keep"
    raw = (root / "backend" / ".env").read_text()
    assert "AUTH_PASSWORD_HASH='$argon2id$" in raw
    assert (root / "backend" / ".env").stat().st_mode & 0o777 == 0o600
    assert (root / "frontend" / ".env.local").stat().st_mode & 0o777 == 0o600


def test_dev_login_keeps_existing_user_and_secret(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path, "AUTH_USERNAME=alice\nSESSION_SECRET=" + "k" * 40 + "\n")

    cli.dev_login(root)

    backend = cli._read_env(root / "backend" / ".env")
    assert backend["AUTH_USERNAME"] == "alice"
    assert backend["SESSION_SECRET"] == "k" * 40
    assert "AUTH_PASSWORD_HASH" in backend


def test_dev_login_never_prints_the_password(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _fake_repo(tmp_path)

    cli.dev_login(root)

    password = cli._read_env(root / "frontend" / ".env.local")["VITE_DEV_LOGIN_PASSWORD"]
    assert password not in capsys.readouterr().out
