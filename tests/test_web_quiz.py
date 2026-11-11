"""The web quiz's brain (ADR 0014): phases and clicks, no Streamlit.

Real cards, answers and sentence bank, cut down to a few words in a temp cards file;
progress, judge cache and seen file in tmp_path. Live sentences off (no Claude).
"""

import json

import pytest

from hsk_trainer.quiz_setup import (
    CARDS_FILE,
    NOT_MARKED,
    QuizFiles,
    QuizOptions,
    build_quiz,
)
from hsk_trainer.web_quiz import WebQuiz
from quizkit.blocks.progress_store import ProgressStore
from quizkit.models import Verdict

WITH_SENTENCE = ["爱", "八"]
NO_SENTENCE = ["边", "车"]

COULDNT = Verdict(correct=False, reason="is offline", source="not_checked")
SAYS_NO = Verdict(correct=False, reason="not that", source="claude")


def judge_saying(verdict):
    class FakeJudge:
        def __init__(self, subject, **kwargs):
            pass

        def __call__(self, question, typed):
            return verdict

    return FakeJudge


def files_with(tmp_path, ids):
    lines = [
        line
        for line in CARDS_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
        if json.loads(line)["id"] in ids
    ]
    assert len(lines) == len(ids)
    cards = tmp_path / "cards.jsonl"
    cards.write_text("".join(lines), encoding="utf-8")
    return QuizFiles(
        cards=cards,
        seen=tmp_path / "seen.json",
        progress=tmp_path / "progress.db",
        judge_cache=tmp_path / "judge_cache.jsonl",
    )


def options(files, order, **given):
    """Options whose deck is dealt in `order` (a seed found by trying)."""
    given = {"live": False, "judge": False, "n": len(order), **given}
    for seed in range(500):
        opts = QuizOptions(seed=seed, **given)
        dealt = build_quiz(opts, files).questions
        if [q.card_id for q in dealt] == order:
            return opts
    raise AssertionError(f"no seed deals {order}")


def started(tmp_path, order, ids=None, judge_class=None, **given):
    files = files_with(tmp_path, ids or order)
    opts = options(files, order, **given)
    files.progress.unlink(missing_ok=True)  # finding the seed made it: start clean
    quiz = WebQuiz(judge_class=judge_class or judge_saying(COULDNT), files=files)
    quiz.start(opts)
    return quiz


def right_answer(quiz):
    return quiz._quiz.current.accepted_answers[0]


def saved(quiz, skill):
    path = quiz.files.progress
    if not path.exists():
        return {}
    return ProgressStore(path).boxes(skill)


# --- word modes ---------------------------------------------------------------------


def test_starts_on_question_one(tmp_path):
    quiz = started(tmp_path, ["爱", "八"])
    assert quiz.phase == "asking"
    assert (quiz.view.card_id, quiz.view.number, quiz.view.total) == ("爱", 1, 2)
    assert quiz.view.shown == ["爱"]
    assert quiz.view.sentence == []


def test_reading_the_page_changes_nothing(tmp_path):
    """Streamlit reruns the page on every click: drawing must not move on."""
    quiz = started(tmp_path, ["爱", "八"], mode="char_sentence")
    seen_before = quiz.files.seen.read_bytes() if quiz.files.seen.exists() else None
    first = quiz.view
    for _ in range(5):
        assert quiz.view is first
        assert quiz.phase == "asking"
    after = quiz.files.seen.read_bytes() if quiz.files.seen.exists() else None
    assert after == seen_before
    assert not quiz.files.progress.exists() or saved(quiz, "recognise") == {}


def test_right_answer_is_saved_then_shown(tmp_path):
    quiz = started(tmp_path, ["爱", "八"])
    quiz.submit(right_answer(quiz), "爱")
    assert quiz.phase == "result"
    assert quiz.result.right and quiz.result.headline == "✅"
    assert saved(quiz, "recognise")["爱"].box == 2  # new + right -> box 2


def test_wrong_word_answer_never_asks_for_your_mark(tmp_path):
    """Word modes: the judge couldn't check -> ❌ with the reason, as in the terminal."""
    quiz = started(tmp_path, ["爱", "八"], judge=True)
    quiz.submit("banana", "爱")
    assert quiz.phase == "result"
    assert not quiz.result.right
    assert quiz.result.details == ["(judge is offline)"]


def test_next_moves_on_once_and_ends_with_the_score(tmp_path):
    quiz = started(tmp_path, ["爱", "八"])
    quiz.submit(right_answer(quiz), "爱")
    quiz.next("爱")
    quiz.next("爱")  # a double click: ignored
    assert (quiz.phase, quiz.view.card_id, quiz.view.number) == ("asking", "八", 2)
    quiz.submit("banana", "八")
    quiz.next("八")
    assert quiz.phase == "ended"
    assert quiz.summary[0] == "Score: 1/2"
    # A new word answered wrong starts in box 1 and stays there.
    assert quiz.summary[1] == "Boxes: 1 word moved up, 0 back to box 1, 1 stayed."


def test_stale_clicks_are_ignored(tmp_path):
    quiz = started(tmp_path, ["爱", "八"])
    quiz.submit("x", "八")  # not the current question
    assert quiz.phase == "asking" and quiz._quiz.result().answered == 0
    quiz.mark(True, "爱")  # nothing waiting for a mark
    quiz.next("爱")  # no result yet
    assert quiz.phase == "asking" and quiz.view.card_id == "爱"
    quiz.submit("x", "爱")
    quiz.submit("x", "爱")  # a second Enter on the same question
    assert quiz._quiz.result().answered == 1
    quiz.start(QuizOptions())  # Start while a quiz runs
    assert quiz.view.card_id == "爱" and quiz.phase == "result"


def test_stop_keeps_the_score_so_far(tmp_path):
    quiz = started(tmp_path, ["爱", "八"])
    quiz.submit(right_answer(quiz), "爱")
    quiz.stop()
    assert quiz.phase == "ended"
    assert quiz.summary[:2] == ["Stopped after 1 of 2.", "Score: 1/1"]


def test_new_quiz_goes_back_to_the_settings(tmp_path):
    quiz = started(tmp_path, ["爱"])
    quiz.new_quiz()  # not ended yet: ignored
    assert quiz.phase == "asking"
    quiz.stop()
    quiz.new_quiz()
    assert (quiz.phase, quiz.view, quiz.summary) == ("setup", None, [])


def test_setup_problem_is_shown_not_raised(tmp_path):
    quiz = WebQuiz(files=QuizFiles(cards=tmp_path / "none.jsonl"))
    quiz.start(QuizOptions())
    assert quiz.phase == "setup"
    assert quiz.problems[0].startswith("No cards file at")


def test_fewer_words_than_asked_says_so(tmp_path):
    files = files_with(tmp_path, ["爱"])
    quiz = WebQuiz(files=files)
    quiz.start(QuizOptions(n=5, judge=False, live=False))
    assert quiz.intro == ["Only 1 band-1 words, so the quiz has 1."]


def test_a_save_problem_is_a_warning_and_the_quiz_goes_on(tmp_path, monkeypatch):
    quiz = started(tmp_path, ["爱", "八"])

    def broken(*args, **kwargs):
        raise ValueError("database is locked")

    monkeypatch.setattr("hsk_trainer.quiz_setup.save_attempt", broken)
    quiz.submit("banana", "爱")
    assert quiz.result.warning == "⚠️ Couldn't save this answer: database is locked"
    quiz.next("爱")
    assert quiz.phase == "asking"


def test_save_off_writes_nothing(tmp_path):
    quiz = started(tmp_path, ["爱"], save=False)
    quiz.submit(right_answer(quiz), "爱")
    quiz.next("爱")
    assert quiz.phase == "ended"
    assert not quiz.files.progress.exists()


# --- sentence modes -------------------------------------------------------------------


def test_sentence_mode_shows_the_sentence_and_its_english_after(tmp_path):
    quiz = started(tmp_path, ["爱", "边"], mode="char_sentence")
    assert len(quiz.view.sentence) == 1 and "爱" in quiz.view.sentence[0]
    quiz.submit(right_answer(quiz), "爱")
    assert quiz.result.after[0].startswith("= ")
    quiz.next("爱")
    assert quiz.view.sentence == ["(no example sentence yet for this word)"]


# --- translate modes ------------------------------------------------------------------


def test_several_skips_are_all_reported(tmp_path):
    quiz = started(tmp_path, ["边", "车", "爱"], mode="translate")
    assert quiz.view.card_id == "爱" and quiz.view.number == 3
    assert quiz.view.notes == [
        "skipped 边: no example sentence yet",
        "skipped 车: no example sentence yet",
    ]
    assert quiz.view.shown[0] != "爱"  # the sentence, not the word


@pytest.mark.parametrize(("got_it", "right"), [(True, True), (False, False)])
def test_gist_mark_is_saved_as_your_own(tmp_path, got_it, right):
    quiz = started(tmp_path, ["爱", "八"], mode="translate", judge=True)
    english = right_answer(quiz)
    quiz.submit("something else entirely", "爱")
    assert quiz.phase == "own_mark"
    assert quiz.marking.english == english
    assert quiz.marking.why == "the judge couldn't check: is offline"
    assert not quiz.files.progress.exists() or saved(quiz, "sentence") == {}
    quiz.mark(got_it, "八")  # meant for another question: ignored
    assert quiz.phase == "own_mark"
    quiz.mark(got_it, "爱")
    assert quiz.phase == "result" and quiz.result.right is right
    assert quiz.result.after[0] == f"= {english}"
    box = saved(quiz, "sentence")["爱"].box
    assert box == (2 if right else 1)
    quiz.mark(got_it, "爱")  # a second click: ignored
    assert quiz._quiz.result().answered == 1


def test_gist_without_the_judge_asks_with_no_reason(tmp_path):
    quiz = started(tmp_path, ["爱"], mode="translate")
    quiz.submit("no idea", "爱")
    assert quiz.phase == "own_mark" and quiz.marking.why is None


def test_judge_verdict_needs_no_mark(tmp_path):
    quiz = started(
        tmp_path,
        ["爱"],
        mode="translate",
        judge=True,
        judge_class=judge_saying(SAYS_NO),
    )
    quiz.submit("no idea", "爱")
    assert quiz.phase == "result"
    assert quiz.result.details == ["judge: not that"]


def test_stop_at_the_gist_question_saves_not_marked_and_the_box_stays(tmp_path):
    quiz = started(tmp_path, ["爱", "八"], mode="translate")
    quiz.submit("no idea", "爱")
    quiz.stop()
    assert quiz.phase == "ended"
    store = ProgressStore(quiz.files.progress)
    assert "爱" not in store.boxes("sentence")  # not checked: no box moved
    assert quiz.summary[0] == "Stopped after 1 of 2."
    assert NOT_MARKED.source == "not_checked"


def test_nothing_to_score_names_the_page_switch(tmp_path):
    quiz = started(tmp_path, ["边", "车"], mode="translate")
    assert quiz.phase == "ended"
    assert quiz.summary == [
        "(skipped 边: no example sentence yet)",
        "(skipped 车: no example sentence yet)",
        "Skipped 2 with no example sentence.",
        "Nothing to score: no word had a sentence (turn on Live sentences).",
    ]
