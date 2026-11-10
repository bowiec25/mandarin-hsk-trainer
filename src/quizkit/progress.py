"""Save one marked answer and move its Leitner box (ADR 0013).

Glue between three blocks: the engine's `Attempt`, the `leitner` rule and the
`progress_store` filing cabinet. Generic: any quiz can call it from its `tell`.
"""

from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from quizkit.blocks.engine import Attempt
from quizkit.blocks.leitner import DEFAULT_RULE, LeitnerRule, next_box
from quizkit.blocks.progress_store import (
    AnswerRecord,
    BoxState,
    DecidedBy,
    ProgressStore,
)


def who_decided(attempt: Attempt) -> DecidedBy:
    """Who marked it: the answer list (exact or a typo), or the judge's source."""
    if attempt.grade.correct:
        return "typo" if attempt.grade.typo else "grader"
    if attempt.verdict is None:  # the list said wrong and no judge was asked
        return "grader"
    return attempt.verdict.source


def save_attempt(
    store: ProgressStore,
    attempt: Attempt,
    skill: str,
    at: datetime,
    rule: LeitnerRule = DEFAULT_RULE,
) -> tuple[BoxState | None, BoxState | None]:
    """Save the answer and its new box in one go; return (old note, new note).

    A "couldn't check" answer is saved as wrong (as the quiz scored it) but its box
    doesn't move: the new note is None.
    """
    who = who_decided(attempt)
    card_id = attempt.question.card_id
    old = store.box(card_id, skill)
    new = next_box(
        old, card_id, skill, None if who == "not_checked" else attempt.correct, at, rule
    )
    store.record(
        AnswerRecord(
            at=at,
            card_id=card_id,
            skill=skill,
            mode=attempt.question.mode,
            typed=attempt.typed,
            correct=attempt.correct,
            decided_by=who,
        ),
        new,
    )
    return old, new


class SkillStats(BaseModel):
    """How one skill is going over a set of cards (for a stats screen, ADR 0013)."""

    model_config = ConfigDict(frozen=True)

    cards: int  # how many cards were asked about
    new: int  # never answered for this skill
    by_box: dict[int, int]  # box -> how many cards are in it (only boxes in use)
    due: int  # due now (or overdue)
    recent_answered: int  # checked answers in the last `days` days
    recent_right: int
    recent_unchecked: int  # answers nobody could mark (not in accuracy)
    most_missed: list[tuple[str, int]]  # (card id, times wrong), most first


def skill_stats(
    store: ProgressStore,
    card_ids: Iterable[str],
    skill: str,
    now: datetime,
    days: int = 7,
    top: int = 10,
) -> SkillStats:
    """Count new / per box / due, recent accuracy and the most-missed cards.

    Only the given cards count (e.g. one band's), so notes for other cards are ignored.
    """
    if now.utcoffset() is None:
        raise ValueError("now must have a timezone (e.g. datetime.now(UTC))")
    ids = set(card_ids)
    notes = [b for cid, b in store.boxes(skill).items() if cid in ids]
    lately = [
        a
        for a in store.answers(since=now - timedelta(days=days), skill=skill)
        if a.card_id in ids
    ]
    recent = [a for a in lately if a.decided_by != "not_checked"]  # someone marked it
    missed = sorted(
        ((b.card_id, b.wrong) for b in notes if b.wrong),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return SkillStats(
        cards=len(ids),
        new=len(ids) - len(notes),
        by_box=dict(sorted(Counter(b.box for b in notes).items())),
        due=sum(b.due <= now for b in notes),
        recent_answered=len(recent),
        recent_right=sum(a.correct for a in recent),
        recent_unchecked=len(lately) - len(recent),
        most_missed=missed[:top],
    )
