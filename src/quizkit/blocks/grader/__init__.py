"""grader: Mark a typed answer right or wrong against a card's answers, forgiving case,
spacing and small typos.

See SPEC.md in this folder (ADR 0003). Generic: no quiz-specific (e.g. Chinese) rules
live here; a quiz passes its own `cleaner` for those.
"""

import re
import unicodedata
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator
from rapidfuzz.distance import OSA

from quizkit.blocks.base import BlockSpec

BLOCK_SPEC = BlockSpec(
    name="grader",
    kind="script",
    goal="Mark a typed answer right or wrong against a card's answers, forgiving case, spacing and small typos.",
    inputs=["answer", "accepted", "cleaner", "GradeSettings"],
    outputs=["Grade"],
)

Cleaner = Callable[[str], list[str]]

_APOSTROPHES = re.compile(r"['’]")  # "one's" -> "ones" (not "one s")
_PUNCTUATION = re.compile(r"[^\w\s]|_")  # anything else that isn't a letter/digit


class GradeSettings(BaseModel):
    """How forgiving the grader is. Defaults are the agreed M3 rules."""

    model_config = ConfigDict(frozen=True)

    allow_typos: bool = True
    one_typo_from: int = Field(default=4, ge=1)
    two_typos_from: int = 8
    ignore_leading: tuple[str, ...] = ("to", "a", "an", "the")

    @model_validator(mode="after")
    def two_after_one(self) -> "GradeSettings":
        if self.two_typos_from <= self.one_typo_from:
            raise ValueError("two_typos_from must be greater than one_typo_from")
        return self


class Grade(BaseModel):
    """The result of grading one answer."""

    model_config = ConfigDict(frozen=True)

    correct: bool
    matched: str | None
    typo: bool
    expected: list[str]


def clean(text: str, settings: GradeSettings) -> str:
    """Normalise text for comparing: NFKC, casefold, no punctuation, single spaces,
    and one leading ignored word ("to love" -> "love")."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = _APOSTROPHES.sub("", text)
    words = _PUNCTUATION.sub(" ", text).split()
    ignored = {w.casefold() for w in settings.ignore_leading}
    if words and words[0] in ignored:
        words = words[1:]
    return " ".join(words)


def typos_allowed(accepted: str, settings: GradeSettings) -> int:
    """How many typos a clean accepted answer allows, by its length (spaces count)."""
    if not settings.allow_typos:
        return 0
    if len(accepted) >= settings.two_typos_from:
        return 2
    if len(accepted) >= settings.one_typo_from:
        return 1
    return 0


def _expected(
    accepted: list[str], cleaner: Cleaner | None, settings: GradeSettings
) -> list[str]:
    """All clean accepted answers, first-seen order, no blanks or duplicates."""
    expected: list[str] = []
    for raw in accepted:
        variants = cleaner(raw) if cleaner else [raw]
        if not isinstance(variants, (list, tuple)):
            raise TypeError(
                f"cleaner must return a list of strings, got {type(variants).__name__} "
                f"for {raw!r}"
            )
        for variant in variants:
            text = clean(variant, settings)
            if text and text not in expected:
                expected.append(text)
    if not expected:
        raise ValueError(
            f"no usable answers to grade against (accepted={accepted!r}): "
            "a card nobody can answer is a data bug"
        )
    return expected


def grade(
    answer: str,
    accepted: list[str],
    cleaner: Cleaner | None = None,
    settings: GradeSettings | None = None,
) -> Grade:
    """Mark `answer` against `accepted` (see SPEC.md). Exact matches beat typo matches."""
    settings = settings or GradeSettings()
    expected = _expected(accepted, cleaner, settings)
    typed = clean(answer, settings)

    if typed and typed in expected:
        return Grade(correct=True, matched=typed, typo=False, expected=expected)

    best: tuple[int, str] | None = None
    if typed:
        for option in expected:
            limit = typos_allowed(option, settings)
            if limit == 0:
                continue
            distance = OSA.distance(typed, option, score_cutoff=limit)
            if distance <= limit and (best is None or distance < best[0]):
                best = (distance, option)

    if best:
        return Grade(correct=True, matched=best[1], typo=True, expected=expected)
    return Grade(correct=False, matched=None, typo=False, expected=expected)
