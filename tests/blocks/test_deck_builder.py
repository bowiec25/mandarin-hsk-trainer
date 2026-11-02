"""deck_builder: contract tests (ID card + SPEC.md) and behaviour tests from SPEC.md."""

from pathlib import Path

import pytest

import quizkit.blocks.deck_builder as block
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.models import Card
from quizkit.modes import MissingFieldError, Mode

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "deck_builder"
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


# --- Behaviour tests (from SPEC.md), toy capitals data only ----------------------

COUNTRY = Mode(name="country", show=["country"])
BOTH = Mode(name="both", show=["country", "continent"])

CAPITALS = [
    ("france", "France", "Europe", "Paris", 1),
    ("spain", "Spain", "Europe", "Madrid", 1),
    ("italy", "Italy", "Europe", "Rome", 1),
    ("japan", "Japan", "Asia", "Tokyo", 1),
    ("peru", "Peru", "South America", "Lima", 2),
    ("kenya", "Kenya", "Africa", "Nairobi", 2),
    ("chile", "Chile", "South America", "Santiago", 2),
    ("laos", "Laos", "Asia", "Vientiane", 3),
    ("mali", "Mali", "Africa", "Bamako", 3),
    ("fiji", "Fiji", "Oceania", "Suva", 3),
]


def make_cards() -> list[Card]:
    return [
        Card(
            id=cid,
            fields={"country": country, "continent": continent},
            answers=[capital, capital.lower()],
            level=level,
        )
        for cid, country, continent, capital, level in CAPITALS
    ]


def ids(deck) -> list[str]:
    return [q.card_id for q in deck]


def levels_of(cards: list[Card]) -> dict[str, int]:
    return {c.id: c.level for c in cards}


# Outputs: only cards at the chosen levels


def test_only_chosen_level_is_used():
    cards = make_cards()
    deck = block.build_deck(cards, COUNTRY, 10, levels=[2], seed=1)
    assert sorted(ids(deck)) == ["chile", "kenya", "peru"]


def test_some_levels_without_cards_is_not_an_error():
    deck = block.build_deck(make_cards(), COUNTRY, 100, levels=[2, 99], seed=1)
    assert sorted(ids(deck)) == ["chile", "kenya", "peru"]


def test_levels_none_means_all_levels():
    cards = make_cards()
    deck = block.build_deck(cards, COUNTRY, 100, levels=None, seed=1)
    assert sorted(ids(deck)) == sorted(c.id for c in cards)


def test_several_levels_together():
    cards = make_cards()
    lv = levels_of(cards)
    deck = block.build_deck(cards, COUNTRY, 100, levels=[1, 3], seed=1)
    assert len(deck) == 7
    assert {lv[i] for i in ids(deck)} == {1, 3}


# Outputs: count and no repeats


def test_returns_exactly_n_questions():
    deck = block.build_deck(make_cards(), COUNTRY, 4, seed=1)
    assert len(deck) == 4


def test_n_bigger_than_available_returns_all_without_error():
    deck = block.build_deck(make_cards(), COUNTRY, 50, levels=[3], seed=1)
    assert sorted(ids(deck)) == ["fiji", "laos", "mali"]


def test_no_card_appears_twice():
    deck = block.build_deck(make_cards(), COUNTRY, 10, seed=7)
    assert len(ids(deck)) == len(set(ids(deck))) == 10


# Outputs: shuffled, repeatable with a seed


def test_same_seed_gives_same_deck():
    a = block.build_deck(make_cards(), COUNTRY, 10, seed=42)
    b = block.build_deck(make_cards(), COUNTRY, 10, seed=42)
    assert a == b


def test_different_seeds_give_different_orders():
    """Across several seeds, more than one order appears (10! orders, so ~certain)."""
    orders = {
        tuple(ids(block.build_deck(make_cards(), COUNTRY, 10, seed=s)))
        for s in range(5)
    }
    assert len(orders) > 1


def test_deck_is_shuffled_not_input_order():
    cards = make_cards()
    orders = {
        tuple(ids(block.build_deck(cards, COUNTRY, 10, seed=s))) for s in range(5)
    }
    assert orders != {tuple(c.id for c in cards)}


def test_seed_does_not_touch_global_random():
    """Uses its own random.Random(seed), so the global generator is left alone."""
    import random

    random.seed(123)
    expected = random.random()
    random.seed(123)
    block.build_deck(make_cards(), COUNTRY, 10, seed=5)
    assert random.random() == expected


# Outputs: each question made with build_question


def test_questions_show_only_the_modes_fields():
    deck = block.build_deck(make_cards(), COUNTRY, 10, seed=1)
    assert all(list(q.shown) == ["country"] for q in deck)
    assert all(q.mode == "country" for q in deck)


def test_multi_field_mode_shows_fields_in_order():
    deck = block.build_deck(make_cards(), BOTH, 10, seed=1)
    assert all(list(q.shown) == ["country", "continent"] for q in deck)


def test_question_content_matches_its_card():
    by_id = {c.id: c for c in make_cards()}
    for q in block.build_deck(make_cards(), BOTH, 10, seed=3):
        card = by_id[q.card_id]
        assert q.shown == {
            "country": card.fields["country"],
            "continent": card.fields["continent"],
        }
        assert q.accepted_answers == card.answers


# Outputs: input not changed


def test_input_cards_list_is_not_changed():
    cards = make_cards()
    before = list(cards)
    block.build_deck(cards, COUNTRY, 5, levels=[1, 2], seed=9)
    assert cards == before


# Failure modes


@pytest.mark.parametrize("n", [0, -1])
def test_n_below_one_raises_value_error(n):
    with pytest.raises(ValueError):
        block.build_deck(make_cards(), COUNTRY, n, seed=1)


def test_empty_cards_raises_value_error():
    with pytest.raises(ValueError):
        block.build_deck([], COUNTRY, 5, seed=1)


def test_no_card_at_chosen_levels_raises_error_naming_levels():
    with pytest.raises(ValueError, match="7"):
        block.build_deck(make_cards(), COUNTRY, 5, levels=[7], seed=1)


def test_empty_levels_list_raises_value_error():
    with pytest.raises(ValueError):
        block.build_deck(make_cards(), COUNTRY, 5, levels=[], seed=1)


def test_missing_field_error_is_passed_through():
    with pytest.raises(MissingFieldError):
        block.build_deck(make_cards(), Mode(name="flag", show=["flag"]), 3, seed=1)


def test_missing_field_fails_every_time_not_only_when_drawn():
    """One broken card among many: n=1 must still fail, for every seed."""
    broken = Card(id="atlantis", fields={"continent": "?"}, answers=["?"], level=1)
    cards = [*make_cards(), broken]
    for seed in range(20):
        with pytest.raises(MissingFieldError):
            block.build_deck(cards, COUNTRY, 1, seed=seed)


@pytest.mark.parametrize("n", [2.0, True, "3"])
def test_n_not_a_whole_number_raises_type_error(n):
    with pytest.raises(TypeError):
        block.build_deck(make_cards(), COUNTRY, n, seed=1)


def test_same_card_id_twice_comes_up_once():
    cards = make_cards()
    deck = block.build_deck([*cards, *cards], COUNTRY, 100, seed=1)
    assert len(deck) == len(cards)
    assert len({q.card_id for q in deck}) == len(cards)


def test_same_card_id_twice_first_copy_wins():
    first = Card(id="x", fields={"country": "First"}, answers=["a"], level=1)
    second = Card(id="x", fields={"country": "Second"}, answers=["b"], level=1)
    deck = block.build_deck([first, second], COUNTRY, 5, seed=1)
    assert len(deck) == 1
    assert deck[0].shown == {"country": "First"}
    assert deck[0].accepted_answers == ["a"]


def test_missing_field_error_is_not_swallowed_into_another_error():
    """MissingFieldError subclasses ValueError; check the exact type survives."""
    with pytest.raises(ValueError) as info:
        block.build_deck(make_cards(), Mode(name="flag", show=["flag"]), 3, seed=1)
    assert type(info.value) is MissingFieldError
