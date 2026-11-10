"""Quiz modes as config: a Mode lists which card fields to show, in order."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from quizkit.models import Card, Question


class MissingFieldError(ValueError):
    """The card doesn't have a field the mode wants to show."""


class Mode(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    show: list[str] = Field(min_length=1)
    # Where the expected answer comes from (ADR 0012): the card's own answers, or
    # the English of a sentence found as each question is asked. build_question
    # always uses the card; for "sentence" the front end swaps the answer in through
    # the engine's `prepare` hook (the HSK CLI does).
    answer_from: Literal["card", "sentence"] = "card"
    # Which skill this mode practises (ADR 0013): progress is kept per card and
    # skill, so modes that test the same thing share one Leitner box.
    skill: str = Field(default="default", min_length=1)


def build_question(card: Card, mode: Mode) -> Question:
    """Turn a Card + Mode into a Question. Fails loudly if a needed field is missing."""
    missing = [f for f in mode.show if f not in card.fields]
    if missing:
        raise MissingFieldError(
            f"card {card.id!r} has no {', '.join(missing)} (needed by mode {mode.name!r})"
        )
    return Question(
        card_id=card.id,
        mode=mode.name,
        shown={f: card.fields[f] for f in mode.show},
        accepted_answers=list(card.answers),
    )
