"""Quiz modes as config: a Mode lists which card fields to show, in order."""

from pydantic import BaseModel, ConfigDict, Field

from quizkit.models import Card, Question


class MissingFieldError(ValueError):
    """The card doesn't have a field the mode wants to show."""


class Mode(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    show: list[str] = Field(min_length=1)


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
