"""deck_builder: Pick which cards to quiz (by level, how many, shuffled) and turn each
into a Question for a mode.

See SPEC.md in this folder (ADR 0003). Generic: no quiz-specific rules here. With a
schedule it deals due cards first (ADR 0013).
"""

import random
from collections.abc import Mapping
from datetime import UTC, datetime

from quizkit.blocks.base import BlockSpec
from quizkit.models import Card, Question
from quizkit.modes import Mode, build_question

BLOCK_SPEC = BlockSpec(
    name="deck_builder",
    kind="script",
    goal="Pick which cards to quiz (by level, how many, shuffled) and turn each into a Question for a mode.",
    inputs=["cards", "mode", "n", "levels", "seed", "schedule", "now"],
    outputs=["list[Question]"],
)


def build_deck(
    cards: list[Card],
    mode: Mode,
    n: int,
    levels: list[int] | None = None,
    seed: int | None = None,
    schedule: Mapping[str, datetime] | None = None,
    now: datetime | None = None,
) -> list[Question]:
    """Pick up to `n` shuffled cards at `levels` (None = all) and build their Questions.

    Same `seed` -> same deck. Uses its own random generator, so the global one is
    untouched. Fewer cards than `n` is fine: the caller can tell by the length.

    With a `schedule` (card id -> when it's next due), it deals due cards first (most
    overdue first), then new cards (shuffled), then cards not due yet (soonest first)
    only to fill `n` (ADR 0013). Without one: a plain shuffle.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"n must be a whole number, got {n!r}")
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    if levels is not None and not levels:
        raise ValueError("levels is an empty list: use None for all levels")
    if not cards:
        raise ValueError("no cards to build a deck from")
    if schedule is not None:
        now = datetime.now(UTC) if now is None else now
        if now.tzinfo is None:
            raise ValueError("now must have a timezone (e.g. datetime.now(UTC))")
        wrong_type = sorted(
            cid for cid, due in schedule.items() if not isinstance(due, datetime)
        )
        if wrong_type:  # e.g. a date or text read back from a file
            raise TypeError(f"schedule times must be datetimes: {wrong_type[:5]}")
        naive = sorted(cid for cid, due in schedule.items() if due.tzinfo is None)
        if naive:
            raise ValueError(f"schedule times need a timezone: {naive[:5]}")

    pool: dict[str, Card] = {}  # by id, first copy wins: no card twice
    for card in cards:
        if (levels is None or card.level in levels) and card.id not in pool:
            pool[card.id] = card
    if not pool:
        raise ValueError(f"no cards at levels {sorted(levels or [])}")

    # Build every pool card's question first, so a card the mode doesn't fit fails
    # every time, not only when it happens to be drawn.
    questions = [build_question(card, mode) for card in pool.values()]
    rng = random.Random(seed)
    if schedule is None:
        return rng.sample(questions, k=min(n, len(questions)))

    # Shuffle once, then stable-sort each group: equal due times stay shuffled.
    shuffled = rng.sample(questions, k=len(questions))
    due, new, later = [], [], []
    for q in shuffled:
        when = schedule.get(q.card_id)
        (new if when is None else due if when <= now else later).append(q)
    due.sort(key=lambda q: schedule[q.card_id])
    later.sort(key=lambda q: schedule[q.card_id])
    return (due + new + later)[:n]
