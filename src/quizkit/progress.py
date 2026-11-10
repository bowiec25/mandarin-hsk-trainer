"""Save one marked answer and move its Leitner box (ADR 0013).

Glue between three blocks: the engine's `Attempt`, the `leitner` rule and the
`progress_store` filing cabinet. Generic: any quiz can call it from its `tell`.
"""

from datetime import datetime

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
