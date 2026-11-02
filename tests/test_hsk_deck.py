"""Real-data check for deck_builder: the HSK deck from data/processed/cards.jsonl.

Uses the shared `real_cards` fixture (tests/conftest.py).
"""

import quizkit.blocks.deck_builder as block
from hsk_trainer.modes import HSK_MODES


def test_band1_char_mode_ten_questions_showing_only_hanzi(real_cards):
    by_id = {c.id: c for c in real_cards}
    deck = block.build_deck(real_cards, HSK_MODES["char"], 10, levels=[1], seed=1)
    assert len(deck) == 10
    assert len({q.card_id for q in deck}) == 10
    assert all(by_id[q.card_id].level == 1 for q in deck)
    assert all(list(q.shown) == ["hanzi"] for q in deck)


def test_band2_asking_for_more_than_exist_gives_all_band2(real_cards):
    """The exact count (197) is pinned in test_word_counts.py, not here."""
    deck = block.build_deck(real_cards, HSK_MODES["char"], 500, levels=[2], seed=1)
    band2 = {c.id for c in real_cards if c.level == 2}
    assert len(deck) == len(band2)
    assert {q.card_id for q in deck} == band2
