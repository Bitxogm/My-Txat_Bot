"""Automatic checks for the evaluation battery (evals/questions.yaml)."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Pictographs, dingbats, symbols and the emoji variation selector. Arrows and box drawing are
# fine (they are common in technical answers); the emoji blocks are not.
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U00002b00-\U00002bff\U0000fe0f\U0001f1e6-\U0001f1ff]"
)
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
_WORD = re.compile(r"[a-záéíóúñü]+")
_SPANISH = frozenset(
    "de la que el en y los las del se por un una para con no es como más pero sus este esta"
    " puedes puede si o hay al lo ya también".split()
)
_ENGLISH = frozenset(
    "the and is to of for with this that you are it be can if or on in an as your".split()
)


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    question: str
    must_any: list[list[str]] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)
    personality: str | None = None
    manual: str | None = None
    kind: str | None = None


def _groups(raw: Any) -> list[list[str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("must_any debe ser una lista")
    return [[str(p) for p in g] if isinstance(g, list) else [str(g)] for g in raw]


def load_questions(path: Path) -> list[Question]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise ValueError(f"{path}: se esperaba una lista de preguntas")
    questions: list[Question] = []
    for item in raw:
        if not isinstance(item, dict) or "question" not in item or "id" not in item:
            raise ValueError(f"{path}: cada pregunta necesita id y question")
        question = Question(
            id=str(item["id"]),
            question=str(item["question"]),
            must_any=_groups(item.get("must_any")),
            must_not=[str(p) for p in item.get("must_not") or []],
            personality=item.get("personality"),
            manual=item.get("manual"),
            kind=item.get("kind"),
        )
        for pattern in [p for g in question.must_any for p in g] + question.must_not:
            re.compile(pattern)  # a typo in the YAML fails before calling any model
        questions.append(question)
    return questions


def has_emoji(text: str) -> bool:
    return bool(_EMOJI.search(text))


def is_spanish(text: str) -> bool:
    """Rough language check on the prose (code blocks removed): more Spanish than English
    function words. Short answers with no prose at all pass."""
    words = _WORD.findall(_CODE.sub(" ", text).lower())
    spanish = sum(1 for w in words if w in _SPANISH)
    english = sum(1 for w in words if w in _ENGLISH)
    if spanish + english < 3:
        return True
    return spanish > english


def check(question: Question, answer: str) -> list[str]:
    """Reasons the answer fails the automatic checks; empty when it passes."""
    reasons: list[str] = []
    for group in question.must_any:
        if not any(re.search(p, answer, re.IGNORECASE) for p in group):
            reasons.append(f"falta {' | '.join(group)}")
    for pattern in question.must_not:
        if re.search(pattern, answer, re.IGNORECASE):
            reasons.append(f"contiene {pattern}")
    if has_emoji(answer):
        reasons.append("usa emojis")
    if not is_spanish(answer):
        reasons.append("no está en español")
    return reasons
