"""Shared test helpers (pytest loads this file automatically)."""

from pathlib import Path

import pytest

from quizkit.files import load_cards
from quizkit.models import Card

CARDS_JSONL = Path(__file__).parent.parent / "data" / "processed" / "cards.jsonl"


@pytest.fixture(scope="session")
def real_cards() -> list[Card]:
    """All cards from the committed data/processed/cards.jsonl, loaded once per run."""
    return load_cards(CARDS_JSONL)
