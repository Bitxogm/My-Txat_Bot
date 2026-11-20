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
