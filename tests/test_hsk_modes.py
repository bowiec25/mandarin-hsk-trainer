"""The 4 HSK quiz modes, written as config."""

import pytest

from hsk_trainer.modes import HSK_MODES
from quizkit.models import Card
from quizkit.modes import MissingFieldError, build_question

AI = Card(
    id="hsk1-ai",
    fields={"hanzi": "爱", "pinyin": "ài"},
    answers=["to love", "love"],
    level=1,
)


def test_the_four_modes_exist():
    assert set(HSK_MODES) == {"char", "char_pinyin", "char_sentence", "full"}
    assert HSK_MODES["full"].show == ["hanzi", "pinyin", "sentence", "sentence_pinyin"]


def test_char_mode_shows_only_hanzi():
    q = build_question(AI, HSK_MODES["char"])
    assert q.shown == {"hanzi": "爱"}


def test_char_pinyin_mode():
    q = build_question(AI, HSK_MODES["char_pinyin"])
    assert q.shown == {"hanzi": "爱", "pinyin": "ài"}


def test_sentence_modes_need_sentences_first():
    # Sentences arrive in M4; until then these modes must fail clearly, not silently.
    with pytest.raises(MissingFieldError, match="sentence"):
        build_question(AI, HSK_MODES["full"])
