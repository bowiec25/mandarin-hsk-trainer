"""quizkit.progress: one marked answer -> saved, and its Leitner box moved (ADR 0013).

Toy capitals cards and real SQLite files in tmp_path.
"""

from datetime import UTC, datetime, timedelta

import pytest

from quizkit.blocks.engine import Attempt
from quizkit.blocks.grader import Grade
from quizkit.blocks.progress_store import ProgressStore
from quizkit.models import Question, Verdict
from quizkit.progress import save_attempt, who_decided

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
