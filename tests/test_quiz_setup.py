"""The shared HSK quiz setup (ADR 0014): what both front ends build a quiz from.

It must print nothing (each front end shows things its own way) and report a setup
problem as SetupError lines. Real cards and answers; progress in tmp_path.
"""

import pytest

from hsk_trainer.quiz_setup import (
    GOT_THE_GIST,
    JUDGE_SUBJECT,
    MISSED_IT,
    NOT_MARKED,
    TRANSLATE_SETTINGS,
    TRANSLATE_SUBJECT,
    QuizFiles,
    QuizOptions,
    SetupError,
    build_quiz,
    readable,
)
from quizkit.blocks.engine import QuizSession
from quizkit.blocks.judge import GIST_RUBRIC
from quizkit.models import Question


class FakeJudge:
    """Records how it was built; never called here."""

    def __init__(self, subject, **kwargs):
        self.subject, self.kwargs = subject, kwargs

    def __call__(self, question, typed):  # pragma: no cover - not asked in these tests
        raise AssertionError("not asked")


@pytest.fixture
def files(tmp_path):
    return QuizFiles(
        progress=tmp_path / "progress.db",
        judge_cache=tmp_path / "judge_cache.jsonl",
        seen=tmp_path / "seen.json",
    )


def build(files, **options):
    return build_quiz(QuizOptions(**options), files, judge_class=FakeJudge)


def test_word_quiz_has_the_deck_the_word_judge_and_a_saver(files, capsys):
    hsk = build(files, band=1, n=5, seed=1)
    assert len(hsk.questions) == 5
    assert all(list(q.shown) == ["hanzi"] for q in hsk.questions)
    assert (hsk.mode.name, hsk.mode.skill, hsk.translating) == (
        "char",
        "recognise",
        False,
    )
    assert hsk.judge.subject == JUDGE_SUBJECT
    assert "rubric" not in hsk.judge.kwargs
    assert hsk.saver is not None and hsk.sentences is None and hsk.prepare is None
    assert isinstance(hsk.session(), QuizSession)
    assert capsys.readouterr().out == ""  # the setup prints nothing


def test_translate_quiz_uses_the_gist_judge_no_typos_and_prepare(files):
    hsk = build(files, mode="translate", n=3, seed=1, live=False)
    assert hsk.translating
    assert hsk.settings == TRANSLATE_SETTINGS
    assert hsk.judge.subject == TRANSLATE_SUBJECT
    assert hsk.judge.kwargs["rubric"] == GIST_RUBRIC
    assert hsk.sentences is not None
    assert hsk.prepare == hsk.sentences.translate


def test_switches_off(files):
    hsk = build(files, n=3, seed=1, judge=False, save=False)
    assert hsk.judge is None
    assert hsk.saver is None
    assert not files.progress.exists()


def test_first_quiz_makes_the_progress_file_only_when_ready(files):
    build(files, n=1, seed=1)
    assert files.progress.exists()


def test_same_seed_same_deck_as_the_terminal_had(files):
    a = build(files, n=5, seed=7, save=False).questions
    b = build(files, n=5, seed=7).questions  # empty progress: the same deal
    assert a == b


def test_unknown_mode_is_a_setup_error(files):
    with pytest.raises(SetupError) as err:
        build(files, mode="nope")
    assert "is not a mode" in err.value.lines[0]


def test_missing_cards_file_is_a_setup_error_with_the_fix(files, tmp_path):
    missing = QuizFiles(cards=tmp_path / "nope.jsonl", progress=files.progress)
    with pytest.raises(SetupError) as err:
        build_quiz(QuizOptions(), missing)
    assert err.value.lines[0].startswith("No cards file at")
    assert "normalizer" in err.value.lines[1]
    assert not files.progress.exists()


def test_broken_progress_file_is_a_setup_error_and_left_alone(files):
    files.progress.write_bytes(b"not a database at all, just text" * 10)
    with pytest.raises(SetupError) as err:
        build(files, n=1)
    assert "--no-save" in err.value.lines[-1]
    assert files.progress.read_bytes() == b"not a database at all, just text" * 10


def test_own_mark_verdicts():
    assert (GOT_THE_GIST.correct, GOT_THE_GIST.source) == (True, "self")
    assert (MISSED_IT.correct, MISSED_IT.source) == (False, "self")
    assert (NOT_MARKED.correct, NOT_MARKED.source) == (False, "not_checked")


def test_readable_keeps_answers_as_written():
    q = Question(
        card_id="x", mode="m", shown={"w": "x"}, accepted_answers=["haven't", "to love"]
    )
    assert list(readable(q).values()) == ["haven't", "to love"]


def test_default_progress_file_follows_the_safety_net(tmp_path):
    """conftest points PROGRESS_FILE at a temp file; QuizFiles() must read it then."""
    assert QuizFiles().progress == tmp_path / "progress.db"
