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
        _check_time("now", now)

    pool: dict[str, Card] = {}  # by id, first copy wins: no card twice
    for card in cards:
        if (levels is None or card.level in levels) and card.id not in pool:
            pool[card.id] = card
    if not pool:
        raise ValueError(f"no cards at levels {sorted(levels or [])}")

    # Build every pool card's question first, so a card the mode doesn't fit fails
    # every time, not only when it happens to be drawn.
    questions = [build_question(card, mode) for card in pool.values()]
    # One full shuffle for both paths, so a schedule that knows none of these cards
    # (a first quiz) gives the same deck for a seed as no schedule.
    shuffled = random.Random(seed).sample(questions, k=len(questions))
    if schedule is None:
        return shuffled[:n]

    # Stable-sort each group: equal due times stay shuffled.
    # Only the pool's own schedule entries are read (and checked): a bad entry for a
    # card at another level doesn't stop this deck.
    due: list[tuple[datetime, Question]] = []
    new: list[Question] = []
    later: list[tuple[datetime, Question]] = []
    for q in shuffled:
        if q.card_id not in schedule:
            new.append(q)
            continue
        when = schedule[q.card_id]
        _check_time(f"schedule[{q.card_id!r}]", when)
        if when <= now:  # due right now counts as due
            due.append((when, q))
        else:
            later.append((when, q))
    due.sort(key=lambda pair: pair[0])
    later.sort(key=lambda pair: pair[0])
    return ([q for _, q in due] + new + [q for _, q in later])[:n]


def _check_time(name: str, value: object) -> None:
    """A real, timezone-aware datetime, or a clear error (naive ones can't be compared)."""
    if not isinstance(value, datetime):  # e.g. a date or text read back from a file
        raise TypeError(f"{name} must be a datetime, got {value!r}")
    if value.utcoffset() is None:  # Python's own test for "naive"
        raise ValueError(f"{name} must have a timezone (e.g. datetime.now(UTC))")
