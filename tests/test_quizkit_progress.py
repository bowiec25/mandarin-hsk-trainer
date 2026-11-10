"""quizkit.progress: one marked answer -> saved, and its Leitner box moved (ADR 0013).

Toy capitals cards and real SQLite files in tmp_path.
"""

from datetime import UTC, datetime, timedelta

import pytest

from quizkit.blocks.engine import Attempt
from quizkit.blocks.grader import Grade
from quizkit.blocks.progress_store import AnswerRecord, BoxState, ProgressStore
from quizkit.models import Question, Verdict
from quizkit.progress import save_attempt, skill_stats, who_decided

T0 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
Q = Question(
    card_id="france",
    mode="country",
    shown={"country": "France"},
    accepted_answers=["Paris"],
)


def attempt(correct=False, typo=False, verdict=None, typed="paris"):
    grade = Grade(
        correct=correct,
        matched="Paris" if correct else None,
        typo=typo,
        expected=["Paris"],
    )
    return Attempt(question=Q, typed=typed, grade=grade, verdict=verdict)


def judged(correct, source):
    return Verdict(correct=correct, reason="because", source=source)


@pytest.mark.parametrize(
    ("a", "who"),
    [
        (attempt(correct=True), "grader"),
        (attempt(correct=True, typo=True), "typo"),
        (attempt(), "grader"),
        (attempt(verdict=judged(True, "claude")), "claude"),
        (attempt(verdict=judged(False, "cache")), "cache"),
        (attempt(verdict=judged(True, "self")), "self"),
        (attempt(verdict=judged(False, "not_checked")), "not_checked"),
    ],
    ids=["exact", "typo", "wrong", "claude", "cache", "self", "not-checked"],
)
def test_who_decided(a, who):
    assert who_decided(a) == who


@pytest.fixture
def store(tmp_path):
    return ProgressStore(tmp_path / "progress.db")


def test_right_answer_is_saved_and_a_new_card_goes_to_box_2(store):
    old, new = save_attempt(store, attempt(correct=True), "capital", T0)
    assert old is None
    assert (new.box, new.due) == (2, T0 + timedelta(days=1))
    assert store.box("france", "capital") == new
    [saved] = store.answers()
    assert (saved.card_id, saved.skill, saved.mode, saved.typed) == (
        "france",
        "capital",
        "country",
        "paris",
    )
    assert (saved.correct, saved.decided_by) == (True, "grader")


def test_second_answer_moves_from_the_saved_box(store):
    save_attempt(store, attempt(correct=True), "capital", T0)
    old, new = save_attempt(
        store, attempt(correct=True), "capital", T0 + timedelta(days=1)
    )
    assert (old.box, new.box) == (2, 3)


def test_judge_accepted_counts_as_right(store):
    _, new = save_attempt(store, attempt(verdict=judged(True, "claude")), "capital", T0)
    assert new.box == 2
    assert store.answers()[0].correct is True


def test_wrong_goes_to_box_1(store):
    save_attempt(store, attempt(correct=True), "capital", T0)
    _, new = save_attempt(store, attempt(typed="lyon"), "capital", T0)
    assert new.box == 1
    assert store.answers()[-1].correct is False


def test_not_checked_is_saved_as_wrong_but_the_box_stays(store):
    save_attempt(store, attempt(correct=True), "capital", T0)
    old, new = save_attempt(
        store, attempt(verdict=judged(False, "not_checked")), "capital", T0
    )
    assert new is None
    assert store.box("france", "capital") == old
    last = store.answers()[-1]
    assert (last.correct, last.decided_by) == (False, "not_checked")


def test_skills_keep_separate_boxes(store):
    save_attempt(store, attempt(correct=True), "capital", T0)
    assert store.box("france", "flag") is None


# --- skill_stats: the numbers behind `hsk stats` ----------------------------------


def _put(store, card_id, box, due, wrong=0, at=T0, correct=True, skill="capital"):
    store.record(
        AnswerRecord(
            at=at,
            card_id=card_id,
            skill=skill,
            mode="country",
            typed="x",
            correct=correct,
            decided_by="grader",
        ),
        BoxState(
            card_id=card_id,
            skill=skill,
            box=box,
            due=due,
            last_seen=at,
            right=1,
            wrong=wrong,
        ),
    )


CAPITALS = ["france", "spain", "italy", "japan", "peru"]


def test_stats_with_no_answers_are_all_new(store):
    s = skill_stats(store, CAPITALS, "capital", T0)
    assert (s.cards, s.new, s.by_box, s.due) == (5, 5, {}, 0)
    assert (s.recent_answered, s.recent_right, s.most_missed) == (0, 0, [])


def test_stats_count_boxes_due_and_new(store):
    _put(store, "france", 1, T0 - timedelta(hours=1))
    _put(store, "spain", 3, T0 + timedelta(days=2))
    _put(store, "italy", 3, T0)  # due exactly now counts as due
    s = skill_stats(store, CAPITALS, "capital", T0)
    assert (s.new, s.by_box, s.due) == (2, {1: 1, 3: 2}, 2)


def test_stats_ignore_other_cards_and_other_skills(store):
    _put(store, "kenya", 2, T0)  # not in the list (e.g. another band)
    _put(store, "france", 2, T0, skill="flag")
    s = skill_stats(store, CAPITALS, "capital", T0)
    assert (s.new, s.by_box, s.recent_answered) == (5, {}, 0)


def test_stats_recent_accuracy_is_the_last_7_days_only(store):
    _put(store, "france", 2, T0, at=T0 - timedelta(days=8), correct=True)
    _put(store, "spain", 1, T0, at=T0 - timedelta(days=2), correct=False)
    _put(store, "italy", 2, T0, at=T0 - timedelta(hours=1), correct=True)
    s = skill_stats(store, CAPITALS, "capital", T0)
    assert (s.recent_answered, s.recent_right) == (2, 1)


def test_most_missed_most_first_ties_by_id_and_capped(store):
    _put(store, "spain", 1, T0, wrong=2)
    _put(store, "france", 1, T0, wrong=5)
    _put(store, "italy", 1, T0, wrong=2)
    _put(store, "japan", 2, T0, wrong=0)  # never missed: not listed
    s = skill_stats(store, CAPITALS, "capital", T0, top=2)
    assert s.most_missed == [("france", 5), ("italy", 2)]


def test_stats_need_a_timezone(store):
    with pytest.raises(ValueError):
        skill_stats(store, CAPITALS, "capital", datetime(2026, 11, 10))


def test_stats_leave_unchecked_answers_out_of_accuracy(store):
    _put(store, "france", 2, T0, at=T0 - timedelta(hours=1), correct=True)
    store.record(
        AnswerRecord(
            at=T0 - timedelta(hours=1),
            card_id="spain",
            skill="capital",
            mode="country",
            typed="x",
            correct=False,
            decided_by="not_checked",
        ),
        None,
    )
    s = skill_stats(store, CAPITALS, "capital", T0)
    assert (s.recent_answered, s.recent_right, s.recent_unchecked) == (1, 1, 1)
