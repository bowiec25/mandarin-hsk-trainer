"""Shared test helpers (pytest loads this file automatically)."""

from pathlib import Path

import pytest

from quizkit.models import Card

CARDS_JSONL = Path(__file__).parent.parent / "data" / "processed" / "cards.jsonl"


@pytest.fixture(scope="session")
def real_cards() -> list[Card]:
    """All cards from the committed data/processed/cards.jsonl, loaded once per run."""
    with CARDS_JSONL.open(encoding="utf-8") as f:
        return [Card.model_validate_json(line) for line in f if line.strip()]
