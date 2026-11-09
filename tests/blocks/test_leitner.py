"""Contract test for the leitner block: its ID card and SPEC.md are complete.

Plus behaviour tests from SPEC.md (ADR 0013): one pure function, toy capitals cards only.
"""

import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

import quizkit.blocks.leitner as block
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.progress_store import BoxState

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "leitner"
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


# --- Behaviour tests (from SPEC.md) -----------------------------------------------
# Public names are looked up on `block` inside each test, so the contract tests
# above still run while the block is unbuilt.

T0 = datetime(2026, 11, 10, 9, 0, 0, tzinfo=UTC)
DAY = timedelta(days=1)
DEFAULT_WAITS = [0, 1, 3, 7, 21]  # days, box 1 first (ADR 0013)


def note(box=3, card_id="france", skill="recall", right=4, wrong=2, seen=T0 - DAY):
    return BoxState(
        card_id=card_id,
        skill=skill,
        box=box,
        due=seen + DAY,
        last_seen=seen,
        right=right,
        wrong=wrong,
    )


def move(old, correct, at=T0, card_id="france", skill="recall", **kw):
    return block.next_box(old, card_id, skill, correct, at, **kw)


# Every move


def test_new_card_right_goes_to_box_2():
    assert move(None, True).box == 2


def test_new_card_wrong_goes_to_box_1():
    assert move(None, False).box == 1


def test_box_3_right_goes_to_box_4():
    assert move(note(box=3), True).box == 4


@pytest.mark.parametrize("box", [1, 2, 3, 4])
def test_right_moves_up_one_box(box):
    assert move(note(box=box), True).box == box + 1


def test_last_box_right_stays_in_last_box():
    assert move(note(box=5), True).box == 5


@pytest.mark.parametrize("box", [1, 2, 3, 4, 5])
def test_wrong_sends_any_box_back_to_1(box):
    assert move(note(box=box), False).box == 1


@pytest.mark.parametrize("old", [None, note(box=4)], ids=["new", "box4"])
def test_not_checked_returns_none(old):
    """correct=None: nobody could check it, so the box doesn't move."""
    assert move(old, None) is None


def test_result_is_a_box_state_for_the_same_card_and_skill():
    new = move(note(), True)
    assert isinstance(new, BoxState)
    assert (new.card_id, new.skill) == ("france", "recall")


def test_new_card_result_carries_the_given_card_and_skill():
    new = move(None, True, card_id="japan", skill="flag")
    assert (new.card_id, new.skill) == ("japan", "flag")


# Due times


def test_default_rule_has_five_boxes_waiting_0_1_3_7_21_days():
    assert block.DEFAULT_RULE.waits == tuple(timedelta(days=d) for d in DEFAULT_WAITS)


def test_default_rule_is_used_when_no_rule_given():
    assert move(note(box=3), True) == move(note(box=3), True, rule=block.DEFAULT_RULE)


@pytest.mark.parametrize("new_box", [1, 2, 3, 4, 5])
def test_due_is_at_plus_the_wait_for_the_new_box(new_box):
    old = note(box=new_box - 1) if new_box > 1 else note(box=4)
    new = move(old, new_box > 1)
    assert new.box == new_box
    assert new.due == T0 + timedelta(days=DEFAULT_WAITS[new_box - 1])


def test_new_card_right_is_due_in_one_day():
    assert move(None, True).due == T0 + DAY


def test_wrong_is_due_straight_away():
    assert move(note(box=5), False).due == T0


def test_custom_rule_waits_are_used():
    rule = block.LeitnerRule(waits=(timedelta(hours=1), timedelta(hours=5)))
    assert move(note(box=1), True, rule=rule).due == T0 + timedelta(hours=5)
    assert move(note(box=2), False, rule=rule).due == T0 + timedelta(hours=1)


def test_custom_rule_caps_at_its_own_last_box():
    rule = block.LeitnerRule(waits=(timedelta(0), DAY, 2 * DAY))
    new = move(note(box=3), True, rule=rule)
    assert new.box == 3
    assert new.due == T0 + 2 * DAY


def test_one_box_rule_new_card_right_stays_in_box_1():
    """With only one box there is no box 2 to go to (SPEC gap: assumed capped)."""
    rule = block.LeitnerRule(waits=(DAY,))
    new = move(None, True, rule=rule)
    assert new.box == 1
    assert new.due == T0 + DAY


def test_due_and_last_seen_follow_a_non_utc_at():
    at = datetime(2026, 11, 10, 17, 0, tzinfo=timezone(timedelta(hours=8)))
    new = move(note(box=2), True, at=at)
    assert new.due == at + 3 * DAY
    assert new.last_seen == at


# Counts and last_seen


def test_right_adds_one_to_right_only():
    new = move(note(right=4, wrong=2), True)
    assert (new.right, new.wrong) == (5, 2)


def test_wrong_adds_one_to_wrong_only():
    new = move(note(right=4, wrong=2), False)
    assert (new.right, new.wrong) == (4, 3)


def test_new_card_counts_start_from_zero():
    right, wrong = move(None, True), move(None, False)
    assert (right.right, right.wrong) == (1, 0)
    assert (wrong.right, wrong.wrong) == (0, 1)


def test_last_seen_is_at():
    assert move(note(), True).last_seen == T0
    assert move(None, False).last_seen == T0


def test_old_note_is_not_changed():
    old = note(box=3)
    move(old, True)
    assert (old.box, old.right) == (3, 4)


# Failure modes


def test_old_note_for_another_card_raises_value_error():
    with pytest.raises(ValueError):
        move(note(card_id="spain"), True, card_id="france")


def test_old_note_for_another_skill_raises_value_error():
    with pytest.raises(ValueError):
        move(note(skill="flag"), True, skill="recall")


def test_mismatch_raises_even_when_not_checked():
    """SPEC gap: assumed the mismatch check runs before the correct=None early exit."""
    with pytest.raises(ValueError):
        move(note(card_id="spain"), None, card_id="france")


@pytest.mark.parametrize("correct", [True, None], ids=["right", "unchecked"])
@pytest.mark.parametrize("old", [None, note()], ids=["new", "old"])
def test_at_without_timezone_raises_value_error(old, correct):
    with pytest.raises(ValueError):
        move(old, correct, at=datetime(2026, 11, 10, 9, 0))


def test_at_before_last_seen_is_allowed_and_used_as_given():
    """A clock went back: the result uses `at` as given."""
    earlier = T0 - 10 * DAY
    new = move(note(box=2, seen=T0), True, at=earlier)
    assert new.last_seen == earlier
    assert new.due == earlier + 3 * DAY


def test_old_box_above_last_box_is_treated_as_last_box_when_right():
    rule = block.LeitnerRule(waits=(timedelta(0), DAY, 3 * DAY))
    new = move(note(box=5), True, rule=rule)
    assert new.box == 3
    assert new.due == T0 + 3 * DAY


def test_old_box_above_last_box_wrong_still_goes_to_box_1():
    rule = block.LeitnerRule(waits=(timedelta(0), DAY, 3 * DAY))
    assert move(note(box=5), False, rule=rule).box == 1


@pytest.mark.parametrize(
    "waits",
    [
        (),
        (timedelta(days=-1),),
        (timedelta(0), timedelta(hours=-1)),
        (timedelta(0), 3 * DAY, DAY),
    ],
    ids=["no-boxes", "negative", "negative-later", "shorter"],
)
def test_bad_rule_raises_validation_error(waits):
    with pytest.raises(ValidationError):
        block.LeitnerRule(waits=waits)


def test_equal_waits_are_allowed():
    """'At least as long as the one before' allows equal waits."""
    assert len(block.LeitnerRule(waits=(DAY, DAY)).waits) == 2


def test_rule_is_frozen():
    with pytest.raises(ValidationError):
        block.DEFAULT_RULE.waits = (DAY,)


# Generic

CJK = re.compile(r"[㐀-鿿豈-﫿]")


def test_block_code_has_no_chinese():
    for py in Path(block.__file__).parent.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert not CJK.search(text), f"{py.name}: {CJK.findall(text)}"
        assert not re.search(r"hsk|mandarin|pinyin", text, re.IGNORECASE), py.name


def test_new_right_box_is_a_rule_setting():
    from datetime import UTC

    rule = block.LeitnerRule(
        waits=tuple(timedelta(days=d) for d in (0, 1, 2, 4, 8, 16)), new_right_box=3
    )
    at = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
    new = block.next_box(None, "france", "recall", True, at, rule=rule)
    assert new.box == 3
    assert new.due == at + timedelta(days=2)


def test_rule_refuses_a_wait_over_ten_years():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        block.LeitnerRule(waits=(timedelta(0), timedelta(days=10**6)))
    with pytest.raises(ValidationError):
        block.LeitnerRule(waits=(timedelta(0),), new_right_box=0)
