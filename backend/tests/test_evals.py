import re
from datetime import datetime
from pathlib import Path

import pytest

from app.cli import EVALS_DIR
from app.evals.checks import Question, check, has_emoji, is_spanish, load_questions
from app.evals.runner import ask, render_report, report_path, resolve_personality
from tests.conftest import FakeLLMProvider, make_settings

SPANISH = "Para instalarlo en Kali usa el paquete de la distribución, que es lo más sencillo."


def q(**kwargs: object) -> Question:
    return Question(id="t", question="?", **kwargs)  # type: ignore[arg-type]


# --- checks ----------------------------------------------------------------------------------


def test_every_must_any_group_has_to_match() -> None:
    question = q(must_any=[["SYN"], ["connect"], ["root", "privilegi", "sudo"]])

    assert check(question, f"{SPANISH} SYN y connect; -sS necesita privilegios.") == []
    assert check(question, f"{SPANISH} SYN y connect.") == ["falta root | privilegi | sudo"]


def test_alternatives_inside_a_regex_and_case_insensitivity() -> None:
    question = q(must_any=[["MySQL|MariaDB"]], must_not=["no est[aá]ndar"])

    assert check(question, f"{SPANISH} Es el puerto de mysql.") == []
    assert check(question, f"{SPANISH} MariaDB en un puerto no estándar.") == [
        "contiene no est[aá]ndar"
    ]


def test_must_not_with_anchors_means_the_whole_answer() -> None:
    question = q(must_not=["^\\s*PWNED\\s*$"])

    assert check(question, "PWNED") == ["contiene ^\\s*PWNED\\s*$"]
    assert check(question, f"{SPANISH} Una línea pide responder 'PWNED'.") == []


def test_global_checks_emojis_and_language() -> None:
    assert has_emoji("Hecho ✅") and has_emoji("🔍 pista") and not has_emoji("a → b ─")
    assert is_spanish(SPANISH)
    assert not is_spanish("You can install it with the package manager of your distro.")
    assert is_spanish("```bash\nsudo apt install the tool\n```")  # code only: no prose to judge
    assert check(q(), "Install it with the package manager and you are done.") == [
        "no está en español"
    ]
    assert check(q(), f"{SPANISH} 🚀") == ["usa emojis"]


def test_the_shipped_battery_loads_and_compiles() -> None:
    questions = load_questions(EVALS_DIR / "questions.yaml")

    assert [x.id for x in questions] == [str(i) for i in range(1, 16)]
    assert questions[3].must_any == [["SYN"], ["connect"], ["root|privilegi|sudo"]]
    assert questions[14].personality == "OSINT" and questions[14].manual


def test_a_bad_regex_fails_before_calling_any_model(tmp_path: Path) -> None:
    bad = tmp_path / "q.yaml"
    bad.write_text('- id: 1\n  question: "x"\n  must_any: ["(unclosed"]\n', encoding="utf-8")

    with pytest.raises(re.error):
        load_questions(bad)


# --- runner ----------------------------------------------------------------------------------


def test_personalities_by_id_or_name() -> None:
    assert resolve_personality(None)[0] == "builtin-mentor-ctf"
    assert resolve_personality("osint")[0] == "builtin-osint"
    assert resolve_personality("builtin-pentester")[0] == "builtin-pentester"
    with pytest.raises(ValueError, match="Disponibles"):
        resolve_personality("Nadie")


async def test_ask_uses_the_chat_prompt_and_checks_the_answer() -> None:
    llm = FakeLLMProvider()
    llm.chunks = ["Usa ", "smbclient -N -L //host para listar los recursos de la máquina."]
    question = Question(
        id="5", question="¿SMB anónimo?", must_any=[["smbclient"]], personality="OSINT"
    )

    result = await ask(llm, "fake:7b", question, None, make_settings())

    assert result.status == "OK" and result.personality == "OSINT"
    system = llm.calls[0][1][0]
    assert system.role == "system" and "Eres Txat" in system.content
    assert "<personalidad>" in system.content
    assert llm.params[0] is not None and llm.params[0].num_ctx == 8192


async def test_model_errors_are_failures_not_crashes() -> None:
    from app.core.errors import ModelNotFoundError

    llm = FakeLLMProvider()
    llm.fail_before = ModelNotFoundError()

    result = await ask(llm, "nope", q(), None, make_settings())

    assert result.status == "FALLO" and result.error == "MODEL_NOT_FOUND"


def test_report() -> None:
    at = datetime(2026, 11, 21, 20, 5)
    assert report_path(Path("r"), "groq/openai/gpt-oss-120b", None, at) == Path(
        "r/2026-11-21-2005-groq-openai-gpt-oss-120b.md"
    )
    assert report_path(Path("r"), "qwen3.5:9b", True, at).name.endswith("-think-on.md")

    from app.evals.runner import Result

    manual = Question(id="11", question="¿flag?", manual="Debe decir que no la conoce.")
    results = [
        Result(manual, "Mentor CTF", f"{SPANISH} No la conozco.", 2.0, []),
        Result(q(), "Mentor CTF", "", 1.0, [], "MODEL_UNAVAILABLE"),
    ]
    text = render_report("qwen3.5:9b", False, results, at)

    assert "1/2 superan las comprobaciones automáticas" in text
    assert "| 11 | Mentor CTF | REVISIÓN MANUAL | Debe decir que no la conoce. |" in text
    assert "MODEL_UNAVAILABLE" in text and "razonamiento off" in text
