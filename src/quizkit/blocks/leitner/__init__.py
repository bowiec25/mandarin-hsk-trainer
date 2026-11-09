"""leitner: Move a card's box after an answer (right: up one, wrong: back to box 1) and say when it's next due.

See SPEC.md in this folder (ADR 0003, ADR 0013). The teacher who moves the flashcards:
one pure function and its settings. `progress_store` files what it returns.
"""

from datetime import datetime, timedelta
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field, field_validator

from quizkit.blocks.base import BlockSpec
from quizkit.blocks.progress_store import BoxState

BLOCK_SPEC = BlockSpec(
    name="leitner",
    kind="script",
    goal="Move a card's box after an answer (right: up one, wrong: back to box 1) and say when it's next due.",
    inputs=["old", "card_id", "skill", "correct", "at", "rule"],
    outputs=["BoxState", "None"],  # None when the answer couldn't be checked
)

__all__ = ["BLOCK_SPEC", "DEFAULT_RULE", "LeitnerRule", "next_box"]


MAX_WAIT = timedelta(days=3650)  # ten years: longer is a typo, and would overflow


class LeitnerRule(BaseModel):
    """How long each box waits before its cards are due again (box 1 first)."""

    model_config = ConfigDict(frozen=True)

    waits: tuple[timedelta, ...]
    # A new card answered right: known the first time, so it skips ahead (the user's
    # choice, 2026-11-10: box 2 waits a day instead of coming straight back).
    new_right_box: int = Field(default=2, ge=1)

    @field_validator("waits")
    @classmethod
    def _sensible(cls, waits: tuple[timedelta, ...]) -> tuple[timedelta, ...]:
        if not waits:
            raise ValueError("a rule needs at least one box")
        if any(w < timedelta(0) for w in waits):
            raise ValueError("a wait can't be negative")
        if any(w > MAX_WAIT for w in waits):
            raise ValueError(f"a wait can't be longer than {MAX_WAIT.days} days")
        if any(later < earlier for earlier, later in pairwise(waits)):
            raise ValueError("each box must wait at least as long as the one before")
        return waits


# ADR 0013: 5 boxes, waiting 0 / 1 / 3 / 7 / 21 days (a guess: tune after real use).
DEFAULT_RULE = LeitnerRule(
    waits=tuple(timedelta(days=d) for d in (0, 1, 3, 7, 21)),
)


def next_box(
    old: BoxState | None,
    card_id: str,
    skill: str,
    correct: bool | None,
    at: datetime,
    rule: LeitnerRule = DEFAULT_RULE,
) -> BoxState | None:
    """The card's new note after this answer, or None if it couldn't be checked."""
    if at.tzinfo is None:
        raise ValueError("at must have a timezone (e.g. datetime.now(UTC))")
    if old is not None and (old.card_id, old.skill) != (card_id, skill):
        raise ValueError(
            f"the old note is for {old.card_id!r} / {old.skill!r}, not "
            f"{card_id!r} / {skill!r}"
        )
    if correct is None:  # nobody could check it: leave the box alone (ADR 0013)
        return None
    last = len(rule.waits)
    if not correct:
        box = 1
    elif old is None:
        box = min(rule.new_right_box, last)
    else:
        box = min(old.box + 1, last)  # an old box above the last counts as the last
    right, wrong = (old.right, old.wrong) if old else (0, 0)
    right, wrong = (right + 1, wrong) if correct else (right, wrong + 1)
    return BoxState(
        card_id=card_id,
        skill=skill,
        box=box,
        due=at + rule.waits[box - 1],
        last_seen=at,
        right=right,
        wrong=wrong,
    )
