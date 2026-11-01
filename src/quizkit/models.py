"""Generic data shapes: Card (one item to learn) and Question (one quiz turn).

Nothing here knows about Chinese. A Card's `fields` are named by the specific quiz
(e.g. {"country": ...} for a capitals quiz; each quiz picks its own field names).
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
