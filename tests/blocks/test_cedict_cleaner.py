"""Tests for the cedict_cleaner block: contract (ID card + SPEC) and behaviour (from SPEC.md)."""

import re
from pathlib import Path

import pytest

import hsk_trainer.blocks.cedict_cleaner as block
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.grader import grade
from quizkit.models import Card

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "cedict_cleaner"
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


# ---- Behaviour (from SPEC.md) ----------------------------------------------------
# Called as block.clean_answer (not imported at the top), so the contract tests above
# still run before the block is built.

CARDS_JSONL = Path(__file__).parents[2] / "data" / "processed" / "cards.jsonl"
HANZI = re.compile(r"[㐀-鿿]")


def clean(meaning: str) -> list[str]:
    return block.clean_answer(meaning)


def load_cards() -> list[Card]:
    with CARDS_JSONL.open(encoding="utf-8") as f:
        return [Card.model_validate_json(line) for line in f if line.strip()]


# Rule 1: drop meanings that aren't the HSK meaning


@pytest.mark.parametrize(
    "meaning",
    [
        "surname Bai",
        "abbr. for 超级市场",
        "also written 哪儿[na3 r5]",
        "also pr. [yi2]",
        "Taiwan pr. [ji1]",
        "variant of 么[me5]",
        "old variant of 么[me5]",
        "see 什么[shen2 me5]",
        "used in 琵琶[pi2 pa5]",
    ],
)
def test_rule1_non_hsk_meanings_are_dropped(meaning):
    assert clean(meaning) == []


# Rule 2: remove (...) notes and [...] pinyin


def test_rule2_label_note_is_removed():
    assert clean("(coll.) father") == ["father"]


def test_rule2_pinyin_in_square_brackets_is_removed():
    result = clean("a kind of tea [cha2]")
    assert result == ["a kind of tea"]


# Rule 3: a one-plain-word note also gives a version with it, plainest first


def test_rule3_plain_word_note_also_kept():
    assert clean("(cooked) rice") == ["rice", "cooked rice"]


@pytest.mark.parametrize(
    ("meaning", "expected"),
    [
        ("(Tw) bus", ["bus"]),
        ("(slang) cool", ["cool"]),
        ("to help (sb)", ["to help"]),
        ("(coll.) father", ["father"]),
    ],
)
def test_rule3_label_notes_do_not_make_an_extra_version(meaning, expected):
    assert clean(meaning) == expected


# Rule 4: remove placeholder words sb, sth, etc and ... / …


def test_rule4_sb_is_removed():
    assert clean("to let sb off lightly") == ["to let off lightly"]


def test_rule4_possessive_placeholder_is_removed_whole():
    """Real meaning of 该: no stray "'s" left behind."""
    assert clean("to be sb's turn to do sth") == ["to be turn to do"]


@pytest.mark.parametrize(
    ("meaning", "expected"),
    [
        ("to do sth", ["to do"]),
        ("fruits etc", ["fruits"]),
        ("...right?", ["right?"]),
        ("…OK?", ["OK?"]),
    ],
)
def test_rule4_other_placeholders_are_removed(meaning, expected):
    assert clean(meaning) == expected


# Rule 5: colon lists replace the meaning


def test_rule5_colon_list_replaces_meaning():
    meaning = (
        "classifier indicating a small amount or small number greater than 1: "
        "some, a few, several"
    )
    assert clean(meaning) == ["some", "a few", "several"]


# Rule 6: classifiers (no colon) replace the meaning


def test_rule6_classifier_for_gives_the_items():
    assert clean("classifier for vehicles") == ["vehicles"]


def test_rule6_classifier_items_split_on_commas():
    assert clean("classifier for books, magazines") == ["books", "magazines"]


# Rule 7: commas keep the whole meaning and the part before the first comma


def test_rule7_comma_keeps_whole_and_first_part():
    assert clean("date, day of the month") == ["date, day of the month", "date"]


# Rule 8: drop results with Chinese or empty; no duplicates


def test_rule8_results_with_chinese_are_dropped():
    meaning = "the Great Learning, one of the Four Books 四书"
    assert clean(meaning) == ["the Great Learning"]


def test_rule8_extension_a_character_counts_as_chinese():
    assert clean("an old word 㐀") == []


def test_rule8_no_duplicates():
    assert clean("classifier for cars, cars") == ["cars"]


# Failure modes


@pytest.mark.parametrize("meaning", ["", "   ", "\t\n"])
def test_blank_meaning_returns_empty_list(meaning):
    assert clean(meaning) == []


@pytest.mark.parametrize(
    "meaning",
    ["(modal particle indicating suggestion or surmise)", "surname Bai", "(coll.)"],
)
def test_clutter_only_meaning_returns_empty_list(meaning):
    assert clean(meaning) == []


@pytest.mark.parametrize("meaning", ["(coll. father", "father)", "[ba4 father"])
def test_unbalanced_brackets_do_not_crash_and_words_stay(meaning):
    result = clean(meaning)
    assert result, f"{meaning!r} lost all its words"
    assert any("father" in r for r in result)
    for r in result:
        assert not set(r) & set("()[]"), f"leftover bracket in {r!r}"


@pytest.mark.parametrize("meaning", ["to love", "hundred", "Hello World!"])
def test_unknown_pattern_passes_through_unchanged(meaning):
    assert clean(meaning) == [meaning]


# Outputs


@pytest.mark.parametrize(
    "meaning", ["rice", "", "surname Bai", "(cooked) rice", "date, day of the month"]
)
def test_always_returns_a_list_of_strings(meaning):
    result = clean(meaning)
    assert isinstance(result, list)
    assert all(isinstance(r, str) for r in result)


def test_real_meanings_give_clean_unique_nonblank_results():
    """Every meaning in the 978 cards: no brackets, no Chinese, no blanks, no dupes."""
    for card in load_cards():
        for meaning in card.answers:
            result = clean(meaning)
            assert isinstance(result, list), (card.id, meaning)
            assert len(result) == len(set(result)), (card.id, meaning, result)
            for r in result:
                assert r.strip(), (card.id, meaning, result)
                assert not set(r) & set("()[]"), (card.id, meaning, r)
                assert not HANZI.search(r), (card.id, meaning, r)


# Real data: all 978 cards


def test_cards_file_has_978_cards():
    assert len(load_cards()) == 978


def test_every_card_keeps_at_least_one_answer():
    empty = [
        card.id for card in load_cards() if not any(clean(m) for m in card.answers)
    ]
    assert empty == [], f"cards with no typeable answer: {empty}"


def test_grader_accepts_first_clean_answer_of_every_card():
    wrong = []
    for card in load_cards():
        first = next(r for m in card.answers for r in clean(m))
        if not grade(first, card.answers, cleaner=block.clean_answer).correct:
            wrong.append((card.id, first))
    assert wrong == []


def card_by_id(card_id: str) -> Card:
    return next(c for c in load_cards() if c.id == card_id)


@pytest.mark.parametrize(
    ("card_id", "typed"),
    [
        ("爸爸", "father"),
        ("爸爸", "dad"),
        ("米饭", "rice"),
        ("辆", "vehicles"),
        ("些", "a few"),
        ("百", "hundred"),
    ],
)
def test_spot_check_accepted(card_id, typed):
    card = card_by_id(card_id)
    assert grade(typed, card.answers, cleaner=block.clean_answer).correct


def test_spot_check_bai_surname_not_accepted():
    card = card_by_id("百")
    assert not grade("Bai", card.answers, cleaner=block.clean_answer).correct
