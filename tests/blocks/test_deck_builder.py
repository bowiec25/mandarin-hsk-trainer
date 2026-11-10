"""deck_builder: contract tests (ID card + SPEC.md) and behaviour tests from SPEC.md."""

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from types import MappingProxyType

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


# --- Schedule input (M5, ADR 0013 item 4) ----------------------------------------
# Fixed, timezone-aware times. Level 1 pool = france, spain, italy, japan.

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def deal(n, schedule, levels=None, seed=1, mode=COUNTRY, cards=None, **kw):
    """build_deck with a schedule and the fixed NOW (unless `now` is overridden)."""
    kw.setdefault("now", NOW)
    return block.build_deck(
        make_cards() if cards is None else cards,
        mode,
        n,
        levels=levels,
        seed=seed,
        schedule=schedule,
        **kw,
    )


# Outputs: due first, then new, then not-due


def test_due_cards_come_first_most_overdue_first():
    schedule = {
        "japan": NOW - timedelta(hours=2),
        "spain": NOW - 3 * DAY,
        "italy": NOW - DAY,
    }
    assert ids(deal(4, schedule, levels=[1])) == ["spain", "italy", "japan", "france"]


def test_n_smaller_than_due_count_takes_the_most_overdue():
    schedule = {"japan": NOW - DAY, "spain": NOW - 3 * DAY, "italy": NOW - 2 * DAY}
    assert ids(deal(2, schedule, levels=[1])) == ["spain", "italy"]


def test_new_cards_come_after_due_cards():
    schedule = {"peru": NOW - DAY, "laos": NOW - 2 * DAY}
    deck = ids(deal(10, schedule))
    assert deck[:2] == ["laos", "peru"]
    assert sorted(deck[2:]) == sorted(
        c.id for c in make_cards() if c.id not in schedule
    )


def test_new_cards_are_shuffled():
    """Across seeds, the new cards after the due one appear in more than one order."""
    schedule = {"france": NOW - DAY}
    orders = {tuple(ids(deal(10, schedule, seed=s))[1:]) for s in range(5)}
    assert len(orders) > 1


def test_not_due_cards_left_out_when_due_and_new_fill_n():
    schedule = {"france": NOW - DAY, "spain": NOW + DAY, "italy": NOW + 3 * DAY}
    assert ids(deal(2, schedule, levels=[1])) == ["france", "japan"]


def test_not_due_cards_fill_the_rest_soonest_first():
    schedule = {"france": NOW - DAY, "italy": NOW + 3 * DAY, "spain": NOW + DAY}
    assert ids(deal(4, schedule, levels=[1])) == ["france", "japan", "spain", "italy"]


def test_not_due_partial_fill_takes_the_soonest():
    schedule = {"france": NOW - DAY, "italy": NOW + 3 * DAY, "spain": NOW + DAY}
    assert ids(deal(3, schedule, levels=[1])) == ["france", "japan", "spain"]


def test_due_equal_to_now_counts_as_due():
    """If france (due == now) were 'not due', the new cards would come before it."""
    assert ids(deal(4, {"france": NOW}, levels=[1]))[0] == "france"


def test_due_times_in_other_timezones_compare_correctly():
    """19:00 at +08:00 is 11:00 UTC (1h overdue); 10:00 UTC is 2h overdue."""
    plus8 = timezone(timedelta(hours=8))
    schedule = {
        "spain": datetime(2026, 11, 10, 19, 0, tzinfo=plus8),
        "italy": datetime(2026, 11, 10, 10, 0, tzinfo=UTC),
    }
    assert ids(deal(2, schedule, levels=[1])) == ["italy", "spain"]


# Outputs: ties shuffled by seed


def test_same_due_time_ties_are_shuffled_by_seed():
    tied = {c.id: NOW - DAY for c in make_cards()}
    orders = {tuple(ids(deal(10, tied, seed=s))) for s in range(5)}
    assert len(orders) > 1


def test_same_seed_with_schedule_gives_same_deck():
    tied = {c.id: NOW - DAY for c in make_cards()}
    tied["fiji"] = NOW + DAY
    assert deal(10, tied, seed=4) == deal(10, tied, seed=4)


def test_ties_stay_inside_their_group():
    """Ties shuffle only among themselves: the more overdue pair is always first."""
    schedule = {
        "spain": NOW - 2 * DAY,
        "italy": NOW - 2 * DAY,
        "japan": NOW - DAY,
        "france": NOW - DAY,
    }
    for seed in range(5):
        deck = ids(deal(4, schedule, levels=[1], seed=seed))
        assert set(deck[:2]) == {"spain", "italy"}
        assert set(deck[2:]) == {"japan", "france"}


# Outputs: extra ids, empty schedule, no schedule, defaults


def test_schedule_ids_not_in_pool_are_ignored():
    """'atlantis' is unknown and 'peru' is level 2: neither appears, no error."""
    schedule = {"atlantis": NOW - 9 * DAY, "peru": NOW - 5 * DAY, "spain": NOW - DAY}
    deck = ids(deal(10, schedule, levels=[1]))
    assert deck[0] == "spain"
    assert sorted(deck) == ["france", "italy", "japan", "spain"]


def test_empty_schedule_is_a_plain_shuffle_of_new_cards():
    decks = [ids(deal(10, {}, seed=s)) for s in range(5)]
    assert all(sorted(d) == sorted(c.id for c in make_cards()) for d in decks)
    assert len({tuple(d) for d in decks}) > 1


def test_schedule_knowing_no_pool_card_gives_the_same_deck_as_none():
    """A first quiz (empty store) deals exactly what --seed dealt before."""
    for seed in range(5):
        for n in (1, 4, 10):
            plain = block.build_deck(make_cards(), COUNTRY, n, seed=seed)
            assert deal(n, {}, seed=seed) == plain
            assert deal(n, {"atlantis": NOW}, seed=seed) == plain
            at_1 = block.build_deck(make_cards(), COUNTRY, n, levels=[1], seed=seed)
            assert deal(n, {"peru": NOW}, levels=[1], seed=seed) == at_1


def test_no_schedule_ignores_now():
    plain = block.build_deck(make_cards(), COUNTRY, 10, seed=3)
    with_now = block.build_deck(make_cards(), COUNTRY, 10, seed=3, now=NOW)
    assert with_now == plain


def test_schedule_accepts_any_mapping():
    schedule = MappingProxyType({"italy": NOW - DAY})
    assert ids(deal(4, schedule, levels=[1]))[0] == "italy"


def test_now_defaults_to_current_utc_time():
    """No `now`: times relative to the real clock still sort due / new / not-due."""
    real_now = datetime.now(UTC)
    schedule = {"france": real_now - DAY, "spain": real_now + 30 * DAY}
    deck = ids(
        block.build_deck(
            make_cards(), COUNTRY, 4, levels=[1], seed=1, schedule=schedule
        )
    )
    assert deck[0] == "france"
    assert deck[-1] == "spain"


def test_schedule_questions_still_built_from_their_cards():
    by_id = {c.id: c for c in make_cards()}
    schedule = {"peru": NOW - DAY, "fiji": NOW + DAY}
    for q in deal(10, schedule, mode=BOTH, seed=2):
        assert list(q.shown) == ["country", "continent"]
        assert q.accepted_answers == by_id[q.card_id].answers


def test_schedule_and_cards_are_not_changed():
    cards = make_cards()
    before = list(cards)
    schedule = {"france": NOW - DAY, "spain": NOW + DAY}
    schedule_before = dict(schedule)
    deal(3, schedule, cards=cards)
    assert cards == before
    assert schedule == schedule_before


def test_schedule_with_duplicate_card_ids_deals_each_once():
    cards = make_cards()
    deck = ids(deal(100, {"france": NOW - DAY}, cards=[*cards, *cards]))
    assert len(deck) == len(set(deck)) == len(cards)


# Schedule failure modes


def test_naive_schedule_time_raises_value_error():
    schedule = {"france": datetime(2026, 11, 9, 12, 0)}
    with pytest.raises(ValueError):
        deal(4, schedule, levels=[1])


def test_naive_now_with_schedule_raises_value_error():
    with pytest.raises(ValueError):
        deal(4, {"france": NOW - DAY}, levels=[1], now=datetime(2026, 11, 10, 12, 0))


def test_missing_field_fails_every_time_with_a_schedule():
    """The schedule must not let the deck skip checking a broken card."""
    broken = Card(id="atlantis", fields={"continent": "?"}, answers=["?"], level=1)
    cards = [*make_cards(), broken]
    for seed in range(10):
        with pytest.raises(MissingFieldError):
            deal(1, {"france": NOW - DAY}, cards=cards, seed=seed)


# SPEC gaps the test-writer found, now decided in the SPEC


def test_naive_now_without_schedule_is_ignored():
    deck = block.build_deck(make_cards(), COUNTRY, 3, seed=1, now=datetime(2026, 1, 1))
    assert len(deck) == 3


def test_bad_entry_for_a_card_outside_the_pool_is_ignored():
    """/code-review: one bad row for another level mustn't stop this deck."""
    deck = deal(3, {"atlantis": datetime(2026, 1, 1), "laos": "oops"}, levels=[1])
    assert len(deck) == 3


class _NoOffset(tzinfo):  # a tzinfo that says "no offset": still naive
    def utcoffset(self, dt):
        return None


def test_tzinfo_without_offset_counts_as_naive():
    with pytest.raises(ValueError):
        deal(3, {"france": datetime(2026, 1, 1, tzinfo=_NoOffset())})
    with pytest.raises(ValueError):
        deal(3, {}, now=datetime(2026, 1, 1, tzinfo=_NoOffset()))


@pytest.mark.parametrize("bad", [NOW.date(), "2026-11-10T12:00:00+00:00"])
def test_now_not_a_datetime_raises_type_error(bad):
    with pytest.raises(TypeError):
        deal(3, {}, now=bad)


@pytest.mark.parametrize("bad", [None, NOW.date(), "2026-11-10T12:00:00+00:00"])
def test_schedule_value_not_a_datetime_raises_type_error(bad):
    with pytest.raises(TypeError):
        deal(3, {"france": bad})
