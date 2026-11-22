"""Runs the evaluation battery against models through the same prompt composition and
LLMProvider adapters as the chat (no direct calls to Ollama or the cloud)."""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.api.generation import context_for
from app.core.config import Settings
from app.core.errors import AppError, ModelRateLimitedError
from app.domain.builtin_personalities import BUILTIN_PERSONALITIES
from app.domain.context import Turn, fit_history
from app.domain.personality import DEFAULT_PERSONALITY_ID, PersonalityFields
from app.domain.prompts import compose_system_prompt
from app.evals.checks import Question, check
from app.ports.llm import LLMProvider


@dataclass(frozen=True, slots=True)
class RunInfo:
    """Where a run's model lives and which base prompt it answered with."""

    provider: str | None = None
    local: bool | None = None
    base_version: str | None = None


@dataclass(frozen=True, slots=True)
class Result:
    question: Question
    personality: str
    answer: str
    seconds: float
    reasons: list[str]
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.error or self.reasons:
            return "FALLO"
        return "REVISIÓN MANUAL" if self.question.manual else "OK"


def graded(
    question: Question, personality: str, answer: str, seconds: float, error: str | None
) -> Result:
    """A Result with the checks applied (also used to re-grade saved answers)."""
    if error:
        return Result(question, personality, answer, seconds, [], error)
    verdict = check(question, answer)
    return Result(question, personality, answer, seconds, verdict.reasons, None, verdict.warnings)


def resolve_personality(name: str | None) -> tuple[str, PersonalityFields]:
    """A built-in personality by id ("builtin-osint") or name ("OSINT"), case-insensitive."""
    if name is None:
        return DEFAULT_PERSONALITY_ID, BUILTIN_PERSONALITIES[DEFAULT_PERSONALITY_ID]
    wanted = name.strip().lower()
    for pid, fields in BUILTIN_PERSONALITIES.items():
        if wanted in (pid.lower(), fields.name.lower()):
            return pid, fields
    names = ", ".join(f.name for f in BUILTIN_PERSONALITIES.values())
    raise ValueError(f"Personalidad desconocida: {name}. Disponibles: {names}")


# A provider's rate limit (Groq's free tier: tokens per minute) is not the model's fault: wait
# and ask again instead of counting it as a failure.
RATE_LIMIT_RETRIES = 8
RATE_LIMIT_MAX_WAIT_SECONDS = 90.0

Sleep = Callable[[float], Awaitable[None]]


def rate_limit_wait(exc: ModelRateLimitedError, attempt: int) -> float:
    """Seconds to wait: Retry-After (plus a second) when the provider sends it, else a growing
    backoff."""
    try:
        wait = float(exc.headers.get("Retry-After", ""))
    except ValueError:
        wait = 10.0 * attempt
    return min(max(wait, 1.0) + 1.0, RATE_LIMIT_MAX_WAIT_SECONDS)


async def ask(
    llm: LLMProvider,
    model: str,
    question: Question,
    default_personality: str | None,
    settings: Settings,
    sleep: Sleep = asyncio.sleep,
) -> Result:
    _, personality = resolve_personality(question.personality or default_personality)
    system_prompt = compose_system_prompt(personality.system_prompt)
    budget, params = context_for(model, personality.params, settings)
    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        started = time.perf_counter()
        try:
            fitted = fit_history(
                system_prompt, [], Turn(role="user", text=question.question), budget
            )
            answer = "".join([c async for c in llm.stream_chat(model, fitted.messages, params)])
        except ModelRateLimitedError as exc:
            if attempt == RATE_LIMIT_RETRIES:
                return Result(question, personality.name, "", 0.0, [], exc.code)
            await sleep(rate_limit_wait(exc, attempt))
            continue
        except AppError as exc:
            elapsed = time.perf_counter() - started
            return Result(question, personality.name, "", elapsed, [], exc.code)
        # Only the successful attempt is timed: waiting out the rate limit isn't the model's time.
        elapsed = time.perf_counter() - started
        return graded(question, personality.name, answer, elapsed, None)
    raise AssertionError("unreachable")


def report_path(
    folder: Path, model: str, think: bool | None, at: datetime, personality: str | None = None
) -> Path:
    """Markdown report path; the JSON with the raw answers goes next to it (.json)."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")
    suffix = "" if think is None else ("-think-on" if think else "-think-off")
    if personality:
        suffix += "-" + re.sub(r"[^a-z0-9]+", "-", personality.lower()).strip("-")
    return folder / f"{at:%Y-%m-%d-%H%M}-{slug}{suffix}.md"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _info_text(info: RunInfo | None) -> str:
    if info is None:
        return ""
    parts = []
    if info.provider:
        where = "" if info.local is None else (" (local)" if info.local else " (nube)")
        parts.append(f"proveedor {info.provider}{where}")
    if info.base_version:
        parts.append(f"capa base {info.base_version}")
    return "".join(f" · {p}" for p in parts)


def render_report(
    model: str,
    think: bool | None,
    results: list[Result],
    at: datetime,
    info: RunInfo | None = None,
) -> str:
    automatic = [r for r in results if r.status != "FALLO"]
    warned = [r for r in results if r.warnings]
    seconds = sum(r.seconds for r in results) / len(results) if results else 0.0
    think_text = "" if think is None else f" · razonamiento {'on' if think else 'off'}"
    lines = [
        f"# Evaluación · {model}{think_text}",
        "",
        f"{at:%Y-%m-%d %H:%M} · {len(automatic)}/{len(results)} superan las comprobaciones"
        f" automáticas · {len(warned)} con avisos · {seconds:.1f} s de media{_info_text(info)}",
        "",
        "| # | Personalidad | Resultado | Motivo | Avisos | Segundos | Longitud |",
        "| --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for r in results:
        reason = r.error or "; ".join(r.reasons) or (r.question.manual or "")
        lines.append(
            f"| {r.question.id} | {r.personality} | {r.status} | {_cell(reason)}"
            f" | {_cell('; '.join(r.warnings))} | {r.seconds:.1f} | {len(r.answer)} |"
        )
    lines.append("")
    for r in results:
        kind = f" · {r.question.kind}" if r.question.kind else ""
        lines += [
            f"## {r.question.id}{kind} · {r.status}",
            "",
            "**Pregunta**",
            "",
            *[f"> {line}" for line in r.question.question.splitlines()],
            "",
        ]
        if r.question.manual:
            lines += [f"**Revisar a mano:** {r.question.manual}", ""]
        lines += ["**Respuesta**", "", r.answer or f"_(error: {r.error})_", ""]
    return "\n".join(lines)
