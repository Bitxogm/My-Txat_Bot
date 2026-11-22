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


def fails(question: Question, answer: str) -> list[str]:
    return check(question, answer).reasons


def test_every_must_any_group_has_to_match() -> None:
    question = q(must_any=[["SYN"], ["connect"], ["root", "privilegi", "sudo"]])

    assert fails(question, f"{SPANISH} SYN y connect; -sS necesita privilegios.") == []
    assert fails(question, f"{SPANISH} SYN y connect.") == ["falta root | privilegi | sudo"]


def test_alternatives_inside_a_regex_and_case_insensitivity() -> None:
    question = q(must_any=[["MySQL|MariaDB"]], must_not=["no est[aá]ndar"])

    assert fails(question, f"{SPANISH} Es el puerto de mysql.") == []
    assert fails(question, f"{SPANISH} MariaDB en un puerto no estándar.") == [
        "contiene no est[aá]ndar"
    ]


def test_must_not_with_anchors_means_the_whole_answer() -> None:
    question = q(must_not=["^\\s*PWNED\\s*$"])

    assert fails(question, "PWNED") == ["contiene ^\\s*PWNED\\s*$"]
    assert fails(question, f"{SPANISH} Una línea pide responder 'PWNED'.") == []


def test_warnings_and_emojis_do_not_fail() -> None:
    question = q(warn=["brew"])

    verdict = check(question, f"{SPANISH} En macOS: brew install exiftool 🍺")

    assert verdict.reasons == []
    assert verdict.warnings == ["menciona brew", "usa emojis"]


def test_language_check() -> None:
    assert has_emoji("Hecho ✅") and has_emoji("🔍 pista") and not has_emoji("a → b ─")
    assert is_spanish(SPANISH)
    assert not is_spanish("You can install it with the package manager of your distro.")
    assert is_spanish("```bash\nsudo apt install the tool\n```")  # code only: no prose to judge
    assert fails(q(), "Install it with the package manager and you are done.") == [
        "no está en español"
    ]


def test_p2_only_fails_when_it_calls_3306_non_standard() -> None:
    questions = {x.id: x for x in load_questions(EVALS_DIR / "questions.yaml")}
    p2 = questions["2"]

    wrong = "Base de datos de MySQL expuesta en un puerto no estándar (3306)."
    fine = (
        "Es el puerto de MySQL. Aunque 3306 está registrado para MySQL, en entornos no estándar"
        " algunos lo cambian."
    )
    assert fails(p2, f"{SPANISH} {wrong}")
    assert fails(p2, f"{SPANISH} {fine}") == []
    assert fails(p2, f"{SPANISH} MySQL. El puerto 3306 no es estándar.")


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


class RateLimitedThenOk(FakeLLMProvider):
    def __init__(self, failures: int, retry_after: str | None) -> None:
        super().__init__()
        self.failures = failures
        self.retry_after = retry_after
        self.chunks = [SPANISH]

    def stream_chat(self, model, messages, params=None):  # type: ignore[no-untyped-def]
        from app.core.errors import ModelRateLimitedError

        if self.failures:
            self.failures -= 1
            headers = {"Retry-After": self.retry_after} if self.retry_after else None
            raise ModelRateLimitedError(headers=headers)
        return super().stream_chat(model, messages, params)


async def test_rate_limits_are_waited_out_not_failed() -> None:
    llm = RateLimitedThenOk(failures=2, retry_after="7")
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    result = await ask(llm, "groq/m", q(), None, make_settings(), sleep=sleep)

    assert result.status == "OK"
    assert waits == [8.0, 8.0]  # Retry-After plus a second of margin


async def test_rate_limit_without_retry_after_backs_off_and_eventually_reports() -> None:
    from app.evals.runner import RATE_LIMIT_RETRIES

    llm = RateLimitedThenOk(failures=100, retry_after=None)
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    result = await ask(llm, "groq/m", q(), None, make_settings(), sleep=sleep)

    assert result.error == "MODEL_RATE_LIMITED"
    assert len(waits) == RATE_LIMIT_RETRIES - 1 and waits[0] < waits[1]


# --- saved runs and recheck -----------------------------------------------------------------


def _results() -> list:
    from app.evals.runner import graded

    one = Question(id="1", question="¿exiftool?", must_any=[["libimage-exiftool-perl"]])
    two = Question(id="2", kind="TRAMPA", question="Linea 1\nLinea 2", manual="Revisar.")
    answer = f"{SPANISH}\n\n## Paso 1 · OK\n\n```bash\nsudo apt install libimage-exiftool-perl\n```"
    return [
        graded(one, "Pentester", answer, 1.5, None),
        graded(two, "Mentor CTF", "", 0.2, "MODEL_UNAVAILABLE"),
    ]


def test_json_round_trip() -> None:
    from app.evals.store import run_from_json, run_to_json

    at = datetime(2026, 11, 22, 10, 30)
    run = run_from_json(run_to_json("groq/m", None, at, _results()))

    assert (run.model, run.think, run.at) == ("groq/m", None, at)
    assert run.answers[0].personality == "Pentester" and run.answers[1].error == "MODEL_UNAVAILABLE"


def test_old_markdown_reports_can_be_read_back() -> None:
    from app.evals.store import run_from_markdown

    at = datetime(2026, 11, 21, 19, 46)
    results = _results()
    run = run_from_markdown(render_report("qwen3.5:9b", False, results, at))

    assert (run.model, run.think, run.at) == ("qwen3.5:9b", False, at)
    assert run.answers[0].answer == results[0].answer  # headings inside answers survive
    assert run.answers[0].seconds == 1.5 and run.answers[0].personality == "Pentester"
    assert run.answers[1].answer == "" and run.answers[1].error == "MODEL_UNAVAILABLE"


def test_recheck_regrades_without_calling_a_model(tmp_path: Path) -> None:
    from app.cli import main

    at = datetime(2026, 11, 21, 19, 46)
    report = tmp_path / "2026-11-21-1946-qwen3.5-9b-think-off.md"
    report.write_text(render_report("qwen3.5:9b", False, _results(), at), encoding="utf-8")
    questions = tmp_path / "q.yaml"
    questions.write_text(
        '- id: 1\n  question: "x"\n  must_any: ["paquete-que-no-sale"]\n', encoding="utf-8"
    )

    assert main(["eval", "--recheck", str(report), "--questions", str(questions)]) == 0

    text = report.read_text(encoding="utf-8")
    assert "0/1 superan" in text and "falta paquete-que-no-sale" in text  # id 2 left the battery
    assert report.with_suffix(".json").exists()
