"""Generic data shapes: Card (one item to learn) and Question (one quiz turn).

Nothing here knows about Chinese. A Card's `fields` are named by the specific quiz
(e.g. {"country": ...} for a capitals quiz; each quiz picks its own field names).
"""

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Card(BaseModel):
    """One thing to learn: what can be shown about it, and the accepted answers."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    id: str = Field(min_length=1)
    fields: dict[str, str]
    answers: list[str] = Field(min_length=1)
    level: int = Field(ge=1, description="Difficulty level, 1 = easiest")

    @field_validator("answers")
    @classmethod
    def answers_not_blank(cls, answers: list[str]) -> list[str]:
        cleaned = [a.strip() for a in answers if a.strip()]
        if not cleaned:
            raise ValueError("a card needs at least one non-blank answer")
        return cleaned


class Question(BaseModel):
    """One quiz turn: what the learner sees (in order) and which answers count."""

    model_config = ConfigDict(frozen=True)

    card_id: str
    mode: str
    shown: dict[str, str]
    accepted_answers: list[str]


class Verdict(BaseModel):
    """A judge's answer: right or wrong, why, and who decided (ADR 0007)."""

    model_config = ConfigDict(frozen=True)

    correct: bool
    reason: str
    source: Literal[
        "claude", "cache", "not_checked", "self"
    ]  # self = learner marked it

    @model_validator(mode="after")
    def not_checked_is_wrong(self) -> "Verdict":
        if self.source == "not_checked" and self.correct:
            raise ValueError("a verdict that wasn't checked can't be correct")
        return self


Judge = Callable[[Question, str], Verdict]  # any quiz can plug in its own judge
