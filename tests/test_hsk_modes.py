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


def test_the_six_modes_exist():
    assert set(HSK_MODES) == {
        "char", "char_pinyin", "char_sentence", "full", "translate", "translate_pinyin"
    }  # fmt: skip
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


def test_translate_modes_take_the_answer_from_the_sentence():
    """ADR 0012: the expected answer is the sentence's English, not the word's."""
    assert HSK_MODES["translate"].show == ["sentence"]
    assert HSK_MODES["translate_pinyin"].show == ["sentence", "sentence_pinyin"]
    for name in ("translate", "translate_pinyin"):
        assert HSK_MODES[name].answer_from == "sentence"
    for name in ("char", "char_pinyin", "char_sentence", "full"):
        assert HSK_MODES[name].answer_from == "card"
