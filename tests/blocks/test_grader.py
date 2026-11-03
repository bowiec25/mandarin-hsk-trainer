"""Tests for the grader block: contract (ID card + SPEC) and behaviour (from SPEC.md)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

import quizkit.blocks.grader as block
from quizkit.blocks.base import missing_spec_sections, spec_section

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "grader"
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


# ---- Behaviour (from SPEC.md), English/toy data only -----------------------------
# Called as block.grade / block.GradeSettings / block.Grade (not imported at the top),
# so the contract tests above still run before the block is built.


def grade(answer, accepted, **kwargs):
    return block.grade(answer, accepted, **kwargs)


# Outputs: correct / matched / typo / expected


@pytest.mark.parametrize("answer", ["love", "Love!", "to love", " love ", "LOVE"])
def test_forgives_case_spaces_punctuation_and_leading_to(answer):
    result = grade(answer, ["to love"])
    assert isinstance(result, block.Grade)
    assert result.correct is True
    assert result.typo is False
    assert result.matched == "love"


def test_swapped_letters_count_as_one_typo():
    result = grade("loev", ["to love"])
    assert result.correct is True
    assert result.typo is True
    assert result.matched == "love"


def test_wrong_word_is_marked_wrong_with_no_match():
    result = grade("hate", ["to love"])
    assert result.correct is False
    assert result.matched is None
    assert result.typo is False


def test_expected_lists_all_clean_answers():
    result = grade("hate", ["to love", "to like"])
    assert result.expected == ["love", "like"]


def test_expected_has_no_duplicates():
    result = grade("hate", ["to love", "love", "Love!"])
    assert result.expected == ["love"]


def test_extra_spaces_inside_answer_are_ignored():
    assert grade("ice   cream", ["ice cream"]).correct is True


@pytest.mark.parametrize("answer", ["love", "a love", "the love", "an love"])
def test_leading_a_an_the_are_ignored(answer):
    assert grade(answer, ["the love"]).correct is True


# Typo limits by length of the clean accepted answer: 0 / 1 / 2


def test_short_words_stay_strict():
    assert grade("eat", ["cat"]).correct is False
    assert grade("cat", ["cat"]).correct is True


def test_four_letters_allow_one_typo_not_two():
    assert grade("lose", ["love"]).correct is True
    assert grade("lxse", ["love"]).correct is False


def test_seven_letters_allow_one_typo_not_two():
    assert grade("teachr", ["teacher"]).correct is True
    assert grade("techr", ["teacher"]).correct is False


def test_eight_letters_allow_two_typos_not_three():
    assert grade("conputre", ["computer"]).correct is True  # n for m + swap
    assert grade("conputrx", ["computer"]).correct is False


def test_length_is_counted_on_accepted_answer_not_typed_answer():
    """A long typed answer doesn't earn extra typos against a short accepted one."""
    assert grade("cats", ["cat"]).correct is False


# Failure modes


@pytest.mark.parametrize("answer", ["", "   ", "!!!"])
def test_blank_or_only_punctuation_is_wrong(answer):
    result = grade(answer, ["to love"])
    assert result.correct is False
    assert result.matched is None


@pytest.mark.parametrize("answer", ["to", "the"])
def test_lone_ignored_word_does_not_match_a_longer_answer(answer):
    result = grade(answer, ["to love"])
    assert result.correct is False
    assert result.matched is None


def test_empty_accepted_raises_value_error():
    with pytest.raises(ValueError):
        grade("love", [])


def test_single_answer_empty_once_clean_raises_value_error():
    with pytest.raises(ValueError):
        grade("anything", ["!!!"])


def test_settings_can_be_passed_positionally():
    settings = block.GradeSettings(allow_typos=False)
    assert block.grade("loev", ["love"], settings).correct is False
    assert block.grade("love", ["love"], settings).correct is True


def test_settings_can_be_passed_by_keyword():
    settings = block.GradeSettings(allow_typos=False)
    assert block.grade("loev", ["love"], settings=settings).correct is False


def test_settings_none_uses_defaults():
    assert block.grade("loev", ["love"], None).typo is True
    assert block.grade("loev", ["love"], settings=None).typo is True


def test_exact_match_beats_typo_match():
    """'card' is a typo of 'cart' (listed first) but an exact match for 'card'."""
    result = grade("card", ["cart", "card"])
    assert result.correct is True
    assert result.matched == "card"
    assert result.typo is False


def test_full_width_letters_are_normalised():
    assert grade("ｌｏｖｅ", ["to love"]).correct is True


def test_accented_letters_compare_without_crashing():
    assert grade("café", ["café"]).correct is True
    assert grade("Café", ["café"]).correct is True  # NFKC: combining accent


def test_odd_characters_typed_do_not_crash():
    assert grade("爱", ["to love"]).correct is False


# Settings


def test_default_settings_match_spec():
    s = block.GradeSettings()
    assert s.allow_typos is True
    assert s.one_typo_from == 4
    assert s.two_typos_from == 8
    assert s.ignore_leading == ("to", "a", "an", "the")


def test_typos_off_means_exact_only():
    settings = block.GradeSettings(allow_typos=False)
    assert grade("loev", ["love"], settings=settings).correct is False
    assert grade("Love!", ["love"], settings=settings).correct is True


def test_custom_typo_thresholds_are_respected():
    settings = block.GradeSettings(one_typo_from=3, two_typos_from=5)
    assert grade("eat", ["cat"], settings=settings).correct is True
    assert grade("lxsx", ["love"], settings=settings).correct is False
    assert grade("hxusx", ["house"], settings=settings).correct is True


def test_custom_ignore_leading_is_respected():
    settings = block.GradeSettings(ignore_leading=[])
    assert grade("love", ["to love"], settings=settings).correct is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"one_typo_from": 0},
        {"one_typo_from": -1},
        {"one_typo_from": 5, "two_typos_from": 5},
        {"one_typo_from": 5, "two_typos_from": 3},
    ],
)
def test_invalid_settings_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        block.GradeSettings(**kwargs)


def test_settings_are_frozen():
    settings = block.GradeSettings()
    with pytest.raises(ValidationError):
        settings.allow_typos = False


# Added after SPEC clarifications


def test_accepted_answer_empty_once_clean_is_dropped():
    result = grade("hate", ["!!!", "to love"])
    assert result.expected == ["love"]


def test_all_accepted_answers_empty_once_clean_raises_value_error():
    with pytest.raises(ValueError):
        grade("love", ["!!!", "...", "  "])


@pytest.mark.parametrize("answer", ["pm", "PM", "p.m.", "P.M."])
def test_dotted_abbreviation_matches_without_dots(answer):
    """Real case: an HSK word has the meaning "p.m."; "a.m." must not lose its "a"."""
    assert grade(answer, ["p.m."]).correct is True
    assert grade(answer.replace("p", "a").replace("P", "A"), ["a.m."]).correct is True


@pytest.mark.parametrize("answer", ["one‘s", "oneʼs", "one`s", "one’s"])
def test_other_apostrophe_forms_are_removed(answer):
    result = grade(answer, ["one's"])
    assert result.correct is True
    assert result.typo is False


@pytest.mark.parametrize("answer", ["email", "e-mail", "e mail"])
def test_spacing_and_hyphens_are_an_exact_match_not_a_typo(answer):
    result = grade(answer, ["e-mail"])
    assert result.correct is True
    assert result.typo is False


def test_lone_ignored_word_is_kept_as_a_real_answer():
    """A dictionary meaning can be just "to" (e.g. a preposition): typing it counts."""
    result = grade("to", ["to", "to give"])
    assert result.correct is True
    assert result.matched == "to"
    assert result.expected == ["to", "give"]


def test_lone_ignored_word_can_be_a_typo_of_an_answer():
    """SPEC example: "the" is a normal answer, one typo from "then" (4 letters)."""
    result = grade("the", ["then"])
    assert result.correct is True
    assert result.typo is True
    assert result.matched == "then"


def test_multi_word_length_counts_spaces():
    """'ice cream' is 9 characters, so 2 typos are allowed, not 3."""
    assert grade("ixe crexm", ["ice cream"]).correct is True
    assert grade("ixe xrexm", ["ice cream"]).correct is False


def test_space_tips_length_into_two_typo_band():
    """'hot dogs' is 7 letters but 8 characters with the space: 2 typos allowed."""
    assert grade("hxt dxgs", ["hot dogs"]).correct is True


def test_grade_is_frozen():
    result = grade("love", ["love"])
    with pytest.raises(ValidationError):
        result.correct = False
