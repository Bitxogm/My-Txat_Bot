"""Saved evaluation runs: the raw answers as JSON next to each Markdown report, so they can be
re-graded (`app.cli eval --recheck`) when the checks change, without asking the model again.

Reports written before the JSON existed are read back from their Markdown.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.evals.checks import Question
from app.evals.runner import Result, graded


@dataclass(frozen=True, slots=True)
class SavedAnswer:
    id: str
    personality: str
    answer: str
    seconds: float
    error: str | None


@dataclass(frozen=True, slots=True)
class SavedRun:
    model: str
    think: bool | None
    at: datetime
    answers: list[SavedAnswer]


def run_to_json(model: str, think: bool | None, at: datetime, results: list[Result]) -> str:
    return json.dumps(
        {
            "model": model,
            "think": think,
            "at": at.isoformat(timespec="minutes"),
            "answers": [
                {
                    "id": r.question.id,
                    "personality": r.personality,
                    "answer": r.answer,
                    "seconds": round(r.seconds, 2),
                    "error": r.error,
                }
                for r in results
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def run_from_json(text: str) -> SavedRun:
    data = json.loads(text)
    return SavedRun(
        model=str(data["model"]),
        think=data.get("think"),
        at=datetime.fromisoformat(data["at"]),
        answers=[
            SavedAnswer(
                id=str(a["id"]),
                personality=str(a["personality"]),
                answer=str(a["answer"]),
                seconds=float(a["seconds"]),
                error=a.get("error"),
            )
            for a in data["answers"]
        ],
    )


_TITLE = re.compile(r"^# Evaluación · (?P<model>.+?)(?: · razonamiento (?P<think>on|off))?$")
_WHEN = re.compile(r"^(?P<at>\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · ")
_ROW = re.compile(
    r"^\| (?P<id>[^|]+?) \| (?P<personality>[^|]+?) \| [^|]+ \|.*\| (?P<s>[0-9.]+) \| \d+ \|$"
)
_SECTION = re.compile(r"^## (?P<id>\S+)(?: · [^·]+?)? · (?:OK|FALLO|REVISIÓN MANUAL)$")
_ERROR = re.compile(r"^_\(error: (?P<code>[A-Z_]+)\)_$")


def run_from_markdown(text: str) -> SavedRun:
    """Reads a report written before the JSON existed. Answers are taken verbatim between their
    "**Respuesta**" line and the next question's heading."""
    lines = text.split("\n")
    title = _TITLE.match(lines[0])
    when = _WHEN.match(lines[2]) if len(lines) > 2 else None
    if not title or not when:
        raise ValueError("No parece un informe de la batería de evaluación")
    think = title.group("think")
    rows = {m.group("id"): m for m in map(_ROW.match, lines) if m}

    answers: list[SavedAnswer] = []
    current: str | None = None
    body: list[str] = []
    in_answer = False

    def close() -> None:
        if current is None:
            return
        while body and not body[-1].strip():
            body.pop()
        answer = "\n".join(body)
        error = _ERROR.match(answer)
        row = rows.get(current)
        answers.append(
            SavedAnswer(
                id=current,
                personality=row.group("personality") if row else "",
                answer="" if error else answer,
                seconds=float(row.group("s")) if row else 0.0,
                error=error.group("code") if error else None,
            )
        )

    for line in lines:
        section = _SECTION.match(line)
        if section:
            close()
            current, body, in_answer = section.group("id"), [], False
        elif current is not None and not in_answer and line == "**Respuesta**":
            in_answer, body = True, []
        elif in_answer:
            if not body and not line.strip():
                continue  # the blank line after "**Respuesta**"
            body.append(line)
    close()
    return SavedRun(
        model=title.group("model"),
        think=None if think is None else think == "on",
        at=datetime.strptime(when.group("at"), "%Y-%m-%d %H:%M"),
        answers=answers,
    )


def load_run(path: Path) -> tuple[SavedRun, str]:
    """A saved run from a report (.md or .json) and where it came from ("json" or "markdown")."""
    json_path = path.with_suffix(".json")
    if json_path.exists():
        return run_from_json(json_path.read_text(encoding="utf-8")), "json"
    return run_from_markdown(path.with_suffix(".md").read_text(encoding="utf-8")), "markdown"


def regrade(run: SavedRun, questions: list[Question]) -> tuple[list[Result], list[str]]:
    """The saved answers graded with the current checks, and the ids no longer in the battery."""
    by_id = {q.id: q for q in questions}
    results: list[Result] = []
    missing: list[str] = []
    for saved in run.answers:
        question = by_id.get(saved.id)
        if question is None:
            missing.append(saved.id)
            continue
        results.append(
            graded(question, saved.personality, saved.answer, saved.seconds, saved.error)
        )
    return results, missing
