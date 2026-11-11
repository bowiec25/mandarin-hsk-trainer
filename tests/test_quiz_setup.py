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
    describe,
    end_lines,
    readable,
    unmarked,
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


def test_missing_cards_file_is_a_setup_error_with_the_fix(files, tmp_path, monkeypatch):
    """The real cards file (the default) gets the normalizer hint; another path not."""
    from hsk_trainer import quiz_setup

    monkeypatch.setattr(quiz_setup, "CARDS_FILE", tmp_path / "cards.jsonl")
    with pytest.raises(SetupError) as err:
        build_quiz(QuizOptions(), QuizFiles(progress=files.progress))
    assert err.value.lines[0].startswith("No cards file at")
    assert "normalizer" in err.value.lines[1]
    with pytest.raises(SetupError) as err:
        build_quiz(QuizOptions(), QuizFiles(cards=tmp_path / "other.jsonl"))
    assert len(err.value.lines) == 1
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


def test_default_judge_cache_follows_the_safety_net(tmp_path):
    assert QuizFiles().judge_cache == tmp_path / "judge_cache.jsonl"


def test_your_files_follow_the_environment(monkeypatch, tmp_path):
    """How the safety net works: set once, read by any module and any subprocess."""
    monkeypatch.setenv("HSK_PROGRESS_FILE", str(tmp_path / "elsewhere.db"))
    assert QuizFiles().progress == tmp_path / "elsewhere.db"


def test_default_seen_file_follows_the_safety_net(tmp_path, monkeypatch):
    """The seen-sentences file is yours too (gitignored): tests never touch it."""
    assert QuizFiles().seen == tmp_path / "sentence_seen.json"
    monkeypatch.setenv("HSK_SEEN_FILE", str(tmp_path / "other.json"))
    assert QuizFiles().seen == tmp_path / "other.json"


# --- The shared wording (ADR 0014): what to say about an answer and the end --------

WORD = Question(
    card_id="ai", mode="char", shown={"hanzi": "爱"}, accepted_answers=["to love"]
)
MANY = Question(
    card_id="x",
    mode="char",
    shown={"hanzi": "x"},
    accepted_answers=["one", "two", "three", "four", "five"],
)
SENTENCE = Question(
    card_id="ai",
    mode="translate",
    shown={"sentence": "我爱妈妈。"},
    accepted_answers=["I love my mum."],
)


def answered(question, typed, judge=None, settings=None):
    from quizkit.blocks.grader import GradeSettings

    session = QuizSession([question], settings=settings or GradeSettings(), judge=judge)
    return session.answer(typed)


def says(verdict):
    return lambda question, typed: verdict


def test_describe_word_right_typo_and_wrong():
    assert describe(answered(WORD, "love"), False) == ("✅", [])
    assert describe(answered(WORD, "lovve"), False) == (
        "✅ close enough (typo): to love",
        [],
    )
    assert describe(answered(WORD, "hate"), False) == ("❌ to love", [])
    assert describe(answered(MANY, "six"), False) == ("❌ one; two; three; four …", [])


def test_describe_word_with_a_verdict():
    from quizkit.models import Verdict

    yes = Verdict(correct=True, reason="a synonym", source="claude")
    no = Verdict(correct=False, reason="the opposite", source="cache")
    unsure = Verdict(correct=False, reason="is offline", source="not_checked")
    assert describe(answered(WORD, "adore", says(yes)), False) == (
        "✅ accepted by the Claude judge: a synonym",
        [],
    )
    assert describe(answered(WORD, "hate", says(no)), False) == (
        "❌ to love",
        ["judge: the opposite"],
    )
    assert describe(answered(WORD, "hate", says(unsure)), False) == (
        "❌ to love",
        ["(judge is offline)"],
    )
    assert describe(answered(WORD, "adore", says(GOT_THE_GIST)), False) == (
        "✅ you got the gist",
        [],
    )


def test_describe_translation_never_lists_the_answer():
    """The English is shown by the sentence part, not in the headline."""
    from quizkit.models import Verdict

    yes = Verdict(correct=True, reason="same idea", source="claude")
    no = Verdict(correct=False, reason="wrong person", source="claude")
    s = TRANSLATE_SETTINGS
    assert describe(answered(SENTENCE, "I love my mum", settings=s), True) == ("✅", [])
    assert describe(answered(SENTENCE, "I love mum", says(yes), s), True) == (
        "✅ accepted by the Claude judge: same idea",
        [],
    )
    assert describe(answered(SENTENCE, "You love mum", says(no), s), True) == (
        "❌",
        ["judge: wrong person"],
    )
    assert describe(answered(SENTENCE, "x", says(NOT_MARKED), s), True) == (
        "❌",
        ["(not marked)"],
    )
    assert describe(answered(SENTENCE, "x", says(MISSED_IT), s), True) == ("❌", [])
    assert describe(answered(SENTENCE, "x", settings=s), True) == ("❌", [])


def test_unmarked_keeps_the_answer_and_says_not_marked():
    attempt = answered(SENTENCE, "I like mum", settings=TRANSLATE_SETTINGS)
    left = unmarked(attempt)
    assert (left.question, left.typed, left.grade) == (
        attempt.question,
        attempt.typed,
        attempt.grade,
    )
    assert left.verdict == NOT_MARKED
    assert left.correct is False


class CountingSaver:
    def __init__(self, line):
        self.line = line

    def summary(self):
        return self.line


def test_end_lines_score_and_boxes():
    from quizkit.blocks.engine import QuizResult

    done = QuizResult(attempts=(answered(WORD, "love"), answered(WORD, "x")), total=2)
    assert end_lines(done, live=True, saver=None) == ["Score: 1/2"]
    assert end_lines(done, True, CountingSaver("Boxes: 1 word moved up")) == [
        "Score: 1/2",
        "Boxes: 1 word moved up",
    ]
    assert end_lines(done, True, CountingSaver(None)) == ["Score: 1/2"]


def test_end_lines_stopped_early_and_skipped():
    from quizkit.blocks.engine import QuizResult

    part = QuizResult(attempts=(answered(WORD, "love"),), total=5, skipped=1)
    assert end_lines(part, True, None) == [
        "Skipped 1 with no example sentence.",
        "Stopped after 2 of 5.",
        "Score: 1/1",
    ]


def test_end_lines_nothing_to_score_names_the_fix():
    from quizkit.blocks.engine import QuizResult

    none = QuizResult(attempts=(), total=2, skipped=2)
    assert end_lines(none, False, None)[-1] == (
        "Nothing to score: no word had a sentence (try --live)."
    )
    assert end_lines(none, False, None, live_hint="turn on Live sentences")[-1] == (
        "Nothing to score: no word had a sentence (turn on Live sentences)."
    )
    assert "Claude couldn't write any" in end_lines(none, True, None)[-1]


def test_session_takes_the_front_ends_prepare(files):
    """A front end can wrap prepare (e.g. to collect every skip note)."""
    hsk = build(files, mode="translate", n=2, seed=1, live=False, save=False)
    seen = []

    def wrapped(question):
        seen.append(question.card_id)
        return hsk.prepare(question)

    session = hsk.session(prepare=wrapped)
    _ = session.current  # asks prepare (ours, wrapped)
    assert seen[0] == hsk.questions[0].card_id  # (a word with no sentence: next)
    assert hsk.session(prepare=None).current == hsk.questions[0]  # None = no prepare


def test_describe_word_own_no_does_not_blame_the_judge():
    """A word answer you marked wrong yourself: no judge was asked (code review)."""
    assert describe(answered(WORD, "hate", says(MISSED_IT)), False) == (
        "❌ to love",
        [],
    )


def test_unmarked_refuses_an_answer_the_list_marked_right():
    with pytest.raises(ValueError):
        unmarked(answered(WORD, "love"))


def test_broken_removed_list_is_a_setup_error_naming_it(files, tmp_path):
    """ADR 0015: the removed list is committed data; a broken one names itself."""
    from dataclasses import replace

    broken = tmp_path / "sentences_removed.json"
    broken.write_text("not json", encoding="utf-8")
    with pytest.raises(SetupError) as err:
        build(replace(files, removed=broken), mode="char_sentence", n=1, live=False)
    assert err.value.lines[0] == f"Can't read the removed-sentences list {broken}:"


def test_removed_list_reaches_the_bank(files, tmp_path):
    from dataclasses import replace

    listed = tmp_path / "sentences_removed.json"
    listed.write_text('{"爱": ["我爱我的妈妈。"]}', encoding="utf-8")
    hsk = build(replace(files, removed=listed), mode="char_sentence", n=1, live=False)
    assert hsk.sentences.live.bank.is_removed("爱", "我爱我的妈妈。")


# -- gather_stats: the numbers `hsk stats` prints and the web Stats page shows ---------


def _answer(files, word="爱", correct=True, box=2):
    """One saved answer for `word` (recognise), its box set to `box`."""
    from datetime import UTC, datetime, timedelta

    from quizkit.blocks.progress_store import AnswerRecord, BoxState, ProgressStore

    now = datetime.now(UTC)
    ProgressStore(files.progress).record(
        AnswerRecord(
            at=now,
            card_id=word,
            skill="recognise",
            mode="char",
            typed="x",
            correct=correct,
            decided_by="grader",
        ),
        BoxState(
            card_id=word,
            skill="recognise",
            box=box,
            due=now + timedelta(days=1),
            last_seen=now,
            right=int(correct),
            wrong=int(not correct),
        ),
    )


def test_gather_stats_no_file_or_empty_file_is_none_and_makes_nothing(files):
    from hsk_trainer.quiz_setup import gather_stats

    assert gather_stats(files) is None
    assert not files.progress.exists()
    files.progress.write_bytes(b"")
    assert gather_stats(files) is None
    assert files.progress.read_bytes() == b""


def test_gather_stats_one_band_per_skill_with_labels(files):
    from hsk_trainer.quiz_setup import gather_stats, skills

    _answer(files, "爱", correct=False, box=1)
    report = gather_stats(files, band=1)
    assert [b.band for b in report] == [1]
    band = report[0]
    assert band.words == len(band.label) > 0
    assert band.label["爱"] == "爱 ài"
    assert [s.skill for s in band.skills] == list(skills())
    recognise = band.skills[0]
    assert recognise.modes == skills()["recognise"]
    assert recognise.stats.by_box == {1: 1}
    assert recognise.stats.most_missed == [("爱", 1)]
    assert recognise.stats.recent_answered == 1


def test_gather_stats_without_band_gives_every_band(files):
    from hsk_trainer.quiz_setup import gather_stats

    _answer(files)
    assert [b.band for b in gather_stats(files)] == [1, 2, 3]


def test_gather_stats_broken_progress_is_a_setup_error(files):
    from hsk_trainer.quiz_setup import gather_stats

    files.progress.write_bytes(b"not a database at all, just text" * 10)
    with pytest.raises(SetupError) as err:
        gather_stats(files)
    assert "progress file" in err.value.lines[0]


def test_gather_stats_broken_cards_file_names_it(files, tmp_path):
    from dataclasses import replace

    from hsk_trainer.quiz_setup import gather_stats

    _answer(files)
    bad = tmp_path / "cards.jsonl"
    bad.write_text("not json\n", encoding="utf-8")
    with pytest.raises(SetupError) as err:
        gather_stats(replace(files, cards=bad))
    assert str(bad) in err.value.lines[0]
