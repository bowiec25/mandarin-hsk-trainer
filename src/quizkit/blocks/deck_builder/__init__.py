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
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    if levels is not None and not levels:
        raise ValueError("levels is an empty list: use None for all levels")
    if not cards:
        raise ValueError("no cards to build a deck from")

    wanted = set(levels) if levels is not None else None
    pool = [c for c in cards if wanted is None or c.level in wanted]
    if not pool:
        raise ValueError(f"no cards at levels {sorted(wanted or [])}")

    chosen = random.Random(seed).sample(pool, k=min(n, len(pool)))
    return [build_question(card, mode) for card in chosen]
