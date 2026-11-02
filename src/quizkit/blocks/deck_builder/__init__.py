"""deck_builder: Pick which cards to quiz (by level, how many, shuffled) and turn each
into a Question for a mode.

See SPEC.md in this folder (ADR 0003). Generic: no quiz-specific rules here. In M5 this
is where "which cards next?" gets smarter (docs/FUTURE.md).
"""

import random

from quizkit.blocks.base import BlockSpec
from quizkit.models import Card, Question
from quizkit.modes import Mode, build_question

BLOCK_SPEC = BlockSpec(
    name="deck_builder",
    kind="script",
    goal="Pick which cards to quiz (by level, how many, shuffled) and turn each into a Question for a mode.",
    inputs=["cards", "mode", "n", "levels", "seed"],
    outputs=["list[Question]"],
)


def build_deck(
    cards: list[Card],
    mode: Mode,
    n: int,
    levels: list[int] | None = None,
    seed: int | None = None,
) -> list[Question]:
    """Pick up to `n` shuffled cards at `levels` (None = all) and build their Questions.

    Same `seed` -> same deck. Uses its own random generator, so the global one is
    untouched. Fewer cards than `n` is fine: the caller can tell by the length.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"n must be a whole number, got {n!r}")
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    if levels is not None and not levels:
        raise ValueError("levels is an empty list: use None for all levels")
    if not cards:
        raise ValueError("no cards to build a deck from")

    pool: dict[str, Card] = {}  # by id, first copy wins: no card twice
    for card in cards:
        if (levels is None or card.level in levels) and card.id not in pool:
            pool[card.id] = card
    if not pool:
        raise ValueError(f"no cards at levels {sorted(levels or [])}")

    # Build every pool card's question first, so a card the mode doesn't fit fails
    # every time, not only when it happens to be drawn.
    questions = [build_question(card, mode) for card in pool.values()]
    return random.Random(seed).sample(questions, k=min(n, len(questions)))
