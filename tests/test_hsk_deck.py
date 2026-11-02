"""Real-data check for deck_builder: the HSK deck from data/processed/cards.jsonl."""

from pathlib import Path

import pytest

import quizkit.blocks.deck_builder as block
from hsk_trainer.modes import HSK_MODES
from quizkit.models import Card

CARDS_JSONL = Path(__file__).parent.parent / "data" / "processed" / "cards.jsonl"


@pytest.fixture(scope="module")
def cards() -> list[Card]:
    lines = CARDS_JSONL.read_text(encoding="utf-8").splitlines()
    return [Card.model_validate_json(line) for line in lines if line.strip()]


def test_band1_char_mode_ten_questions_showing_only_hanzi(cards):
    by_id = {c.id: c for c in cards}
    deck = block.build_deck(cards, HSK_MODES["char"], 10, levels=[1], seed=1)
    assert len(deck) == 10
    assert len({q.card_id for q in deck}) == 10
    assert all(by_id[q.card_id].level == 1 for q in deck)
    assert all(list(q.shown) == ["hanzi"] for q in deck)


def test_band2_asking_for_500_gives_all_197(cards):
    deck = block.build_deck(cards, HSK_MODES["char"], 500, levels=[2], seed=1)
    band2 = {c.id for c in cards if c.level == 2}
    assert len(band2) == 197
    assert len(deck) == 197
    assert {q.card_id for q in deck} == band2
