"""Tests for the sentence_validator block: contract (ID card + SPEC.md) and behaviour from SPEC.md."""

from pathlib import Path

import pytest
from pydantic import ValidationError

import hsk_trainer.blocks.sentence_validator as block
from hsk_trainer.blocks.sentence_validator import (
    SentenceCheck,
    SentenceSettings,
    Vocab,
    check_sentence,
)
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.models import Card

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "sentence_validator"
    assert block.BLOCK_SPEC.kind == "script"


def test_spec_md_has_every_section():
    assert missing_spec_sections(SPEC_MD) == []


def test_inputs_and_outputs_match_spec():
    """The code's ID card (BLOCK_SPEC) and the job description (SPEC.md) agree."""
    for field, section in [("inputs", "Inputs"), ("outputs", "Outputs")]:
        listed = getattr(block.BLOCK_SPEC, field)
        text = spec_section(SPEC_MD, section)
        for item in listed:
            assert item in text, (
                f"BLOCK_SPEC.{field} has {item!r}, not in SPEC.md {section}"
            )
        if "TODO" not in text:  # once the SPEC section is filled in...
            assert listed, (
                f"SPEC.md {section} is filled in: copy it into BLOCK_SPEC.{field}"
            )


# --- Behaviour tests, written from SPEC.md (test-first) ---


TOY_BANDS = {
    "我": 1,
    "我们": 1,
    "是": 1,
    "爸爸": 1,
    "医生": 1,
    "吃": 1,
    "饭": 1,
    "一起": 2,
    "已经": 3,
}


def make_card(hanzi: str, level: int) -> Card:
    return Card(id=hanzi, fields={"hanzi": hanzi}, answers=["x"], level=level)


@pytest.fixture(scope="module")
def vocab() -> Vocab:
    return Vocab([make_card(h, b) for h, b in TOY_BANDS.items()])


# Outputs


def test_good_sentence_passes_with_no_reasons(vocab):
    check = check_sentence("我爸爸是医生。", "爸爸", vocab)
    assert isinstance(check, SentenceCheck)
    assert check.passed is True
    assert check.reasons == ()


def test_words_lists_checked_pieces_in_order(vocab):
    check = check_sentence("我爸爸是医生。", "爸爸", vocab)
    assert check.words == ("我", "爸爸", "是", "医生")


def test_sentence_check_is_frozen(vocab):
    check = check_sentence("我爸爸是医生。", "爸爸", vocab)
    with pytest.raises(ValidationError):
        check.passed = False


# Rule 1: only Chinese characters and Chinese punctuation


@pytest.mark.parametrize(
    "sentence", ["我爸爸是A医生。", "我爸爸是1医生。", "我爸爸 是医生。"]
)
def test_latin_digits_or_spaces_fail(vocab, sentence):
    check = check_sentence(sentence, "爸爸", vocab)
    assert check.passed is False
    assert check.reasons


def test_chinese_punctuation_is_allowed(vocab):
    check = check_sentence("我爸爸，是医生！", "爸爸", vocab)
    assert check.passed is True


# Rule 2: the word is in it


def test_missing_word_fails_and_names_it(vocab):
    check = check_sentence("我是医生。", "爸爸", vocab)
    assert check.passed is False
    assert any("爸爸" in r for r in check.reasons)


# Rule 3: length


def test_too_short_fails(vocab):
    check = check_sentence("爸爸。", "爸爸", vocab)
    assert check.passed is False
    assert check.reasons


def test_too_long_fails(vocab):
    check = check_sentence("爸爸" * 11 + "。", "爸爸", vocab)  # 22 chars > 20
    assert check.passed is False
    assert check.reasons


def test_punctuation_not_counted_in_length(vocab):
    """5 Chinese characters plus punctuation fits exactly in 5..5."""
    settings = SentenceSettings(min_chars=5, max_chars=5)
    check = check_sentence("爸爸，是医生。", "爸爸", vocab, settings=settings)
    assert check.passed is True


# Rule 4: every other word allowed


def test_higher_band_word_fails_and_names_word_and_band(vocab):
    check = check_sentence("我们一起吃饭。", "我们", vocab)
    assert check.passed is False
    assert any("一起" in r and "2" in r for r in check.reasons)


def test_lower_band_words_allowed_for_higher_band_card(vocab):
    check = check_sentence("我们已经一起吃饭。", "已经", vocab)
    assert check.passed is True


def test_glued_piece_that_splits_into_allowed_words_passes(vocab):
    check = check_sentence("我爸爸吃饭。", "爸爸", vocab)
    assert check.passed is True
    assert "吃饭" not in check.words
    assert check.words.index("吃") + 1 == check.words.index("饭")


def test_unknown_word_fails_as_not_hsk(vocab):
    check = check_sentence("我爸爸是猫。", "爸爸", vocab)
    assert check.passed is False
    assert any("猫" in r and "not an HSK word" in r for r in check.reasons)


def test_extra_words_are_allowed(vocab):
    settings = SentenceSettings(extra_words=("猫",))
    check = check_sentence("我爸爸是猫。", "爸爸", vocab, settings=settings)
    assert check.passed is True


def test_settings_defaults():
    s = SentenceSettings()
    assert (s.min_chars, s.max_chars, s.extra_words) == (3, 20, ())


def test_settings_is_frozen():
    with pytest.raises(ValidationError):
        SentenceSettings().min_chars = 2


# Failure modes


def test_several_problems_give_several_reasons(vocab):
    check = check_sentence("我是A医生。", "爸爸", vocab)  # word missing + Latin letter
    assert check.passed is False
    assert len(check.reasons) >= 2


@pytest.mark.parametrize("sentence", ["", "   "])
def test_empty_sentence_fails_with_reason(vocab, sentence):
    check = check_sentence(sentence, "爸爸", vocab)
    assert check.passed is False
    assert any("empty sentence" in r for r in check.reasons)


def test_word_not_in_cards_raises_value_error(vocab):
    with pytest.raises(ValueError):
        check_sentence("我是老师。", "老师", vocab)


def test_empty_cards_raise_value_error():
    with pytest.raises(ValueError):
        Vocab([])


def test_duplicate_hanzi_raise_value_error():
    with pytest.raises(ValueError):
        Vocab([make_card("爸爸", 1), make_card("爸爸", 2)])


@pytest.mark.parametrize("kwargs", [{"min_chars": 0}, {"min_chars": 5, "max_chars": 4}])
def test_bad_settings_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        SentenceSettings(**kwargs)


def test_repeated_word_is_fine(vocab):
    check = check_sentence("爸爸是爸爸。", "爸爸", vocab)
    assert check.passed is True
    assert check.words.count("爸爸") == 2


def test_repeated_bad_word_still_fails(vocab):
    check = check_sentence("我们一起一起吃饭。", "我们", vocab)
    assert check.passed is False


# Real data (data/processed/cards.jsonl)


@pytest.fixture(scope="module")
def real_vocab(real_cards) -> Vocab:
    return Vocab(real_cards)


@pytest.mark.parametrize(
    ("sentence", "word"),
    [
        ("我们去学校吃饭。", "学校"),
        ("妈妈在家看电视。", "妈妈"),
        ("你叫什么名字？", "名字"),
    ],
)
def test_real_band1_sentences_pass(real_vocab, sentence, word):
    check = check_sentence(sentence, word, real_vocab)
    assert check.passed is True, check.reasons


def test_real_sentence_with_band2_word_fails_for_band1_word(real_vocab):
    check = check_sentence("明天下午我们一起喝茶吧。", "喝", real_vocab)
    assert check.passed is False
    assert any("一起" in r for r in check.reasons)


# -- Block-review fixes ---------------------------------------------------------------


def _vocab(words: dict[str, int]):
    cards = [
        Card(id=w, fields={"hanzi": w}, answers=["x"], level=band)
        for w, band in words.items()
    ]
    return Vocab(cards)


# -- Option B: "a learner at this band could read it" (user's choice, 2026-11-03) ----


def test_word_built_from_easy_words_passes():
    """电视 (band 2) is made of two band-1 words: readable at band 1 (option B)."""
    vocab = _vocab({"我": 1, "看": 1, "电": 1, "视": 1, "电视": 2})
    check = check_sentence("我看电视。", "我", vocab)
    assert check.passed is True, check.reasons
    assert check.words == ("我", "看", "电", "视")


def test_harder_word_with_no_easy_reading_fails():
    vocab = _vocab({"我": 1, "看": 1, "电视": 2})
    check = check_sentence("我看电视。", "我", vocab)
    assert check.passed is False
    assert any("电视" in r and "2" in r for r in check.reasons), check.reasons


def test_word_only_inside_a_longer_word_says_so():
    """我 inside 我们: the reason names the longer word, not the leftover 们."""
    vocab = _vocab({"我": 1, "我们": 1, "是": 1, "医生": 1})
    check = check_sentence("我们是医生。", "我", vocab)
    assert check.passed is False
    assert check.reasons == ("has 我 only inside 我们, not on its own",)


def test_reading_with_fewest_problems_wins():
    """jieba read 他一起来了 as 他/一/起来/了; any reading works if one is easy."""
    vocab = _vocab({"他": 1, "一": 1, "起来": 2, "一起": 1, "来": 1, "了": 1})
    check = check_sentence("他一起来了。", "来", vocab)
    assert check.passed is True, check.reasons
    assert check.words == ("他", "一起", "来", "了")


def test_real_sentences_jieba_used_to_reject_now_pass(real_cards):
    vocab = Vocab(real_cards)
    for sentence, word in [("我看见他了。", "看"), ("你好吗？", "好")]:
        check = check_sentence(sentence, word, vocab)
        assert check.passed, (sentence, check.reasons)


def test_more_chinese_punctuation_and_zero_are_allowed(real_cards):
    vocab = Vocab(real_cards)
    for sentence, word in [("我们去吧……", "去"), ("二〇二六年。", "年")]:
        reasons = check_sentence(sentence, word, vocab).reasons
        assert not any("aren't Chinese" in r for r in reasons), (sentence, reasons)


# -- /code-review round 2 + block-review round 3 ---------------------------------------


def test_missing_word_still_reports_other_problems(vocab):
    check = check_sentence("我们一起吃饭。", "爸爸", vocab)
    assert any("爸爸" in r for r in check.reasons)
    assert any("一起" in r for r in check.reasons), check.reasons


def test_empty_sentence_has_only_that_reason(vocab):
    assert check_sentence("  ", "爸爸", vocab).reasons == ("empty sentence",)


def test_exactly_three_characters_is_long_enough(vocab):
    check = check_sentence("我吃饭。", "我", vocab)
    assert not any("short" in r for r in check.reasons), check.reasons


def test_zero_counts_toward_length(real_cards):
    settings = SentenceSettings(max_chars=4)
    check = check_sentence("二〇二六年。", "年", Vocab(real_cards), settings)
    assert any("too long: 5" in r for r in check.reasons), check.reasons


@pytest.mark.parametrize(
    "sentence", ["他说：『我吃饭。』", "我吃饭【吧】。", "我吃饭．"]
)
def test_more_chinese_punctuation_passes_rule_one(vocab, sentence):
    reasons = check_sentence(sentence, "我", vocab).reasons
    assert not any("aren't Chinese" in r for r in reasons), reasons


@pytest.mark.parametrize("sentence", ["我吃饭Ｏ。", "我吃饭.", "我吃饭!"])
def test_full_width_letters_and_ascii_punctuation_fail(vocab, sentence):
    reasons = check_sentence(sentence, "我", vocab).reasons
    assert any("aren't Chinese" in r for r in reasons), reasons


def test_word_with_a_non_chinese_character_does_not_crash():
    vocab = _vocab({"T恤": 1, "我": 1, "买": 1})
    check = check_sentence("我买T恤。", "T恤", vocab)
    assert "T恤" in check.words
