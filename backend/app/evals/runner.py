"""Runs the evaluation battery against models through the same prompt composition and
LLMProvider adapters as the chat (no direct calls to Ollama or the cloud)."""

import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.api.generation import context_for
from app.core.config import Settings
from app.core.errors import AppError
from app.domain.builtin_personalities import BUILTIN_PERSONALITIES
from app.domain.context import Turn, fit_history
from app.domain.personality import DEFAULT_PERSONALITY_ID, PersonalityFields
from app.domain.prompts import compose_system_prompt
from app.evals.checks import Question, check
from app.ports.llm import LLMProvider


@dataclass(frozen=True, slots=True)
class Result:
    question: Question
    personality: str
    answer: str
    seconds: float
    reasons: list[str]
    error: str | None = None

    @property
    def status(self) -> str:
        if self.error or self.reasons:
            return "FALLO"
        return "REVISIÓN MANUAL" if self.question.manual else "OK"


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


async def ask(
    llm: LLMProvider,
    model: str,
    question: Question,
    default_personality: str | None,
    settings: Settings,
) -> Result:
    _, personality = resolve_personality(question.personality or default_personality)
    system_prompt = compose_system_prompt(personality.system_prompt)
    budget, params = context_for(model, personality.params, settings)
    started = time.perf_counter()
    try:
        fitted = fit_history(system_prompt, [], Turn(role="user", text=question.question), budget)
        answer = "".join([c async for c in llm.stream_chat(model, fitted.messages, params)])
    except AppError as exc:
        return Result(question, personality.name, "", time.perf_counter() - started, [], exc.code)
    return Result(
        question, personality.name, answer, time.perf_counter() - started, check(question, answer)
    )


def report_path(folder: Path, model: str, think: bool | None, at: datetime) -> Path:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")
    suffix = "" if think is None else ("-think-on" if think else "-think-off")
    return folder / f"{at:%Y-%m-%d-%H%M}-{slug}{suffix}.md"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_report(model: str, think: bool | None, results: list[Result], at: datetime) -> str:
    automatic = [r for r in results if r.status != "FALLO"]
    seconds = sum(r.seconds for r in results) / len(results) if results else 0.0
    think_text = "" if think is None else f" · razonamiento {'on' if think else 'off'}"
    lines = [
        f"# Evaluación · {model}{think_text}",
        "",
        f"{at:%Y-%m-%d %H:%M} · {len(automatic)}/{len(results)} superan las comprobaciones"
        f" automáticas · {seconds:.1f} s de media",
        "",
        "| # | Personalidad | Resultado | Motivo | Segundos | Longitud |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for r in results:
        reason = r.error or "; ".join(r.reasons) or (r.question.manual or "")
        lines.append(
            f"| {r.question.id} | {r.personality} | {r.status} | {_cell(reason)}"
            f" | {r.seconds:.1f} | {len(r.answer)} |"
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
