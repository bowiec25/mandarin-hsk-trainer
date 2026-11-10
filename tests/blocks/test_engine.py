"""Tests for the engine block: contract (ID card + SPEC) and behaviour (from SPEC.md)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

import quizkit.blocks.engine as block
from quizkit.blocks import grader
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.grader import Grade, GradeSettings
from quizkit.models import Question

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "engine"
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


# ---- Behaviour (from SPEC.md), toy English data only -----------------------------
# Called as block.QuizSession / block.run_quiz / block.Attempt / block.QuizResult (not
# imported at the top), so the contract tests above still run before the block is built.


def q(country: str, *answers: str) -> Question:
    return Question(
        card_id=country.lower(),
        mode="capital",
        shown={"country": country},
        accepted_answers=list(answers),
    )


FRANCE = q("France", "Paris")
ITALY = q("Italy", "Rome")
SPAIN = q("Spain", "Madrid")
CAPITALS = [FRANCE, ITALY, SPAIN]


def fake_ask(typed: list[str | None]):
    """An `ask` that returns the next item from `typed` and records each question."""
    answers = iter(typed)
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        return next(answers)

    return ask, asked


def collector():
    told: list = []
    return told.append, told


def play(questions, typed, **kwargs):
    ask, asked = fake_ask(typed)
    tell, told = collector()
    result = block.run_quiz(questions, ask, tell, **kwargs)
    return result, asked, told


# -- run_quiz: Outputs -------------------------------------------------------------


def test_full_quiz_scores_and_records_every_attempt_in_order():
    result, _, _ = play(CAPITALS, ["Paris", "  rome ", "Lisbon"])
    assert isinstance(result, block.QuizResult)
    assert (result.correct, result.answered, result.total) == (2, 3, 3)
    assert result.finished is True
    assert [a.question for a in result.attempts] == CAPITALS
    assert [a.typed for a in result.attempts] == ["Paris", "  rome ", "Lisbon"]
    assert [a.grade.correct for a in result.attempts] == [True, True, False]


def test_attempt_holds_the_graders_verdict():
    result, _, _ = play([FRANCE], ["Lisbon"])
    attempt = result.attempts[0]
    assert isinstance(attempt, block.Attempt)
    assert isinstance(attempt.grade, Grade)
    assert attempt.grade.correct is False
    assert attempt.grade.expected == ["paris"]


def test_typo_counts_as_right():
    result, _, _ = play([FRANCE], ["Pariss"])
    assert result.correct == 1
    assert result.attempts[0].grade.typo is True


def test_attempt_and_result_are_frozen():
    result, _, _ = play([FRANCE], ["Paris"])
    with pytest.raises(ValidationError):
        result.total = 99
    with pytest.raises(ValidationError):
        result.attempts[0].typed = "Rome"


# -- run_quiz: quitting, blanks, tell ----------------------------------------------


def test_quit_stops_at_once_and_returns_result_so_far():
    result, asked, _ = play(CAPITALS, ["Paris", None, "Madrid"])
    assert (result.correct, result.answered, result.total) == (1, 1, 3)
    assert result.finished is False
    assert asked == [FRANCE, ITALY]  # ask not called again after the quit


def test_quit_before_first_question_gives_zero_answered():
    result, asked, told = play(CAPITALS, [None])
    assert (result.correct, result.answered, result.total) == (0, 0, 3)
    assert result.finished is False
    assert result.attempts == ()
    assert len(asked) == 1
    assert told == []


def test_blank_answer_is_wrong_not_a_quit():
    result, asked, _ = play(CAPITALS, ["", "Rome", "Madrid"])
    assert result.answered == 3
    assert result.correct == 2
    assert result.attempts[0].typed == ""
    assert result.attempts[0].grade.correct is False
    assert len(asked) == 3


def test_tell_called_once_per_answer_with_its_attempt():
    result, _, told = play(CAPITALS, ["Paris", "Lisbon", "Madrid"])
    assert told == list(result.attempts)
    assert all(isinstance(t, block.Attempt) for t in told)


def test_tell_not_called_after_quit():
    result, _, told = play(CAPITALS, ["Paris", None])
    assert len(told) == 1
    assert told == list(result.attempts)


# -- settings are passed straight to the grader ---------------------------------


def test_settings_are_passed_to_grader():
    result, _, _ = play([FRANCE], ["Pariss"], settings=GradeSettings(allow_typos=False))
    assert result.correct == 0


def test_session_passes_settings():
    session = block.QuizSession([FRANCE], settings=GradeSettings(allow_typos=False))
    assert session.answer("Pariss").grade.correct is False


# -- QuizSession step by step ------------------------------------------------------


def test_session_steps_through_questions():
    session = block.QuizSession(CAPITALS)
    assert session.current == FRANCE
    assert session.done is False
    attempt = session.answer("Paris")
    assert isinstance(attempt, block.Attempt)
    assert attempt.question == FRANCE and attempt.grade.correct is True
    assert session.current == ITALY
    session.answer("x")
    session.answer("Madrid")
    assert session.done is True
    assert session.current is None


def test_session_defaults_work_without_settings():
    session = block.QuizSession([FRANCE])
    assert session.answer("Pariss").grade.typo is True  # default GradeSettings()


def test_result_partway_through():
    session = block.QuizSession(CAPITALS)
    session.answer("Paris")
    result = session.result()
    assert (result.correct, result.answered, result.total) == (1, 1, 3)
    assert result.finished is False


def test_result_when_done_is_finished():
    session = block.QuizSession([FRANCE])
    session.answer("Paris")
    assert session.result().finished is True


def test_answer_after_last_question_raises_runtime_error():
    session = block.QuizSession([FRANCE])
    session.answer("Paris")
    with pytest.raises(RuntimeError):
        session.answer("Paris")


# -- Failure modes -----------------------------------------------------------------


def test_empty_questions_raises_value_error_on_session():
    with pytest.raises(ValueError):
        block.QuizSession([])


def test_empty_questions_raises_value_error_in_run_quiz():
    ask, asked = fake_ask(["Paris"])
    tell, _ = collector()
    with pytest.raises(ValueError):
        block.run_quiz([], ask, tell)
    assert asked == []


def test_error_from_ask_is_passed_through():
    """Any error other than Ctrl-C is a bug and must be loud."""

    def ask(question: Question) -> str | None:
        raise ValueError("broken ask")

    tell, _ = collector()
    with pytest.raises(ValueError, match="broken ask"):
        block.run_quiz(CAPITALS, ask, tell)


def test_error_from_tell_is_passed_through():
    """Any error other than Ctrl-C is a bug and must be loud."""
    ask, _ = fake_ask(["Paris"])

    def tell(attempt) -> None:
        raise ValueError("broken tell")

    with pytest.raises(ValueError, match="broken tell"):
        block.run_quiz(CAPITALS, ask, tell)


# -- Ctrl-C (KeyboardInterrupt) anywhere in run_quiz's loop is a quit --------------


def run_expecting_no_ctrl_c(questions, ask, tell, **kwargs):
    """Call run_quiz; a KeyboardInterrupt escaping it fails the test.

    (Left uncaught, pytest would treat it as the user aborting the whole test run.)
    """
    try:
        return block.run_quiz(questions, ask, tell, **kwargs)
    except KeyboardInterrupt:
        pytest.fail("KeyboardInterrupt escaped run_quiz: Ctrl-C should be a quit")


def test_ctrl_c_from_ask_after_one_answer_returns_result_so_far():
    typed = iter(["Paris"])
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        try:
            return next(typed)
        except StopIteration:
            raise KeyboardInterrupt from None

    tell, told = collector()
    result = run_expecting_no_ctrl_c(CAPITALS, ask, tell)
    assert (result.correct, result.answered, result.total) == (1, 1, 3)
    assert result.finished is False
    assert asked == [FRANCE, ITALY]  # ask not called again after Ctrl-C
    assert told == list(result.attempts)


def test_ctrl_c_before_first_question_gives_zero_answered():
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        raise KeyboardInterrupt

    tell, told = collector()
    result = run_expecting_no_ctrl_c(CAPITALS, ask, tell)
    assert (result.correct, result.answered, result.total) == (0, 0, 3)
    assert result.finished is False
    assert result.attempts == ()
    assert len(asked) == 1
    assert told == []


def test_ctrl_c_from_tell_still_counts_the_marked_answer():
    """Interrupted while *showing* answer 2: it was already marked, so it counts."""
    ask, asked = fake_ask(["Paris", "Lisbon", "Madrid"])
    told: list = []

    def tell(attempt) -> None:
        told.append(attempt)
        if len(told) == 2:
            raise KeyboardInterrupt

    result = run_expecting_no_ctrl_c(CAPITALS, ask, tell)
    assert (result.correct, result.answered, result.total) == (1, 2, 3)
    assert result.finished is False
    assert [a.typed for a in result.attempts] == ["Paris", "Lisbon"]
    assert asked == [FRANCE, ITALY]  # ask not called again
    assert told == list(result.attempts)  # tell saw both, and wasn't called again


def grade_that_raises(monkeypatch, error, when=lambda: True):
    """Swap the engine's `grade` for one that raises `error` whenever `when()` is true.

    Otherwise it calls the real grader. The engine imports `grade` by name, so this
    patches `quizkit.blocks.engine.grade`.
    """
    real_grade = grader.grade

    def fake_grade(*args, **kwargs):
        if when():
            raise error
        return real_grade(*args, **kwargs)

    monkeypatch.setattr(block, "grade", fake_grade)


def test_ctrl_c_while_grading_does_not_count_that_answer(monkeypatch):
    """Interrupted while *marking* answer 2: it isn't counted.

    QuizSession grades a blank answer per question at creation, so the fake grader is
    only armed once question 2 has been asked (after creation), then interrupts it.
    """
    armed = False
    typed = iter(["Paris", "Lisbon", "Madrid"])
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        nonlocal armed
        asked.append(question)
        armed = len(asked) == 2
        return next(typed)

    grade_that_raises(monkeypatch, KeyboardInterrupt, when=lambda: armed)
    tell, told = collector()
    result = run_expecting_no_ctrl_c(CAPITALS, ask, tell)
    assert (result.correct, result.answered, result.total) == (1, 1, 3)
    assert result.finished is False
    assert [a.typed for a in result.attempts] == ["Paris"]
    assert asked == [FRANCE, ITALY]  # ask not called again
    assert told == list(result.attempts)  # tell not called for the unmarked answer


def test_grader_error_mid_quiz_is_passed_through(monkeypatch):
    """Any error from the grader other than Ctrl-C is a bug and must be loud."""
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        return "Paris"

    grade_that_raises(monkeypatch, RuntimeError("broken grader"), when=lambda: asked)
    tell, told = collector()
    with pytest.raises(RuntimeError, match="broken grader"):
        block.run_quiz([FRANCE], ask, tell)
    assert told == []


def test_same_question_twice_is_asked_twice():
    result, asked, _ = play([FRANCE, FRANCE], ["Paris", "Lyon"])
    assert asked == [FRANCE, FRANCE]
    assert result.answered == 2 and result.total == 2
    assert result.correct == 1


def test_session_keeps_its_own_copy_of_questions():
    questions = [FRANCE, ITALY]
    session = block.QuizSession(questions)
    questions.append(SPAIN)
    questions[1] = SPAIN
    session.answer("Paris")
    assert session.current == ITALY
    session.answer("Rome")
    assert session.done is True
    assert session.result().total == 2


def test_block_folder_parts_exist():
    folder = Path(block.__file__).parent
    assert (folder / "SPEC.md").is_file()
    assert (folder / "__init__.py").is_file()


def test_result_attempts_cannot_be_appended():
    result, _, _ = play([FRANCE], ["Paris"])
    with pytest.raises(AttributeError):
        result.attempts.append(result.attempts[0])  # a tuple has no append
    assert result.answered == 1


@pytest.mark.parametrize("total", [0, -1])
def test_result_rejects_total_below_one(total):
    with pytest.raises(ValidationError):
        block.QuizResult(attempts=(), total=total)


def test_result_rejects_more_attempts_than_total():
    result, _, _ = play([FRANCE, ITALY], ["Paris", "Rome"])
    with pytest.raises(ValidationError):
        block.QuizResult(attempts=result.attempts, total=1)


def test_unanswerable_card_is_found_before_the_first_question():
    unanswerable = q("Nowhere", "   ")
    ask, asked = fake_ask(["Paris", "anything"])
    tell, _ = collector()
    with pytest.raises(ValueError):
        block.run_quiz([FRANCE, unanswerable], ask, tell)
    assert asked == []  # failed before anything was asked, so no answers were lost


def test_ctrl_c_while_creating_the_session_is_passed_through(monkeypatch):
    """SPEC: before the loop there is no score to keep, so Ctrl-C is not swallowed.

    The up-front check grades each question once, so a grader that always raises
    Ctrl-C interrupts the session while it is being created.
    """
    grade_that_raises(monkeypatch, KeyboardInterrupt)
    ask, asked = fake_ask(["Paris"])
    tell, _ = collector()
    with pytest.raises(KeyboardInterrupt):
        block.run_quiz([FRANCE], ask, tell)
    assert asked == []


def test_changing_a_question_after_starting_has_no_effect():
    france = q("France", "Paris")
    session = block.QuizSession([france])
    france.accepted_answers.append("Lyon")  # the list inside a frozen model can change
    assert session.answer("Lyon").grade.correct is False


# -- The judge hook (judge SPEC "The engine hook" + "Engine changes") --------------


def fake_judge(correct: bool, reason: str = "Judged."):
    """A judge (any `(Question, str) -> Verdict`) that records what it was asked."""
    from quizkit.blocks.judge import Verdict

    calls: list[tuple[Question, str]] = []

    def judge(question: Question, typed: str):
        calls.append((question, typed))
        return Verdict(correct=correct, reason=reason, source="claude")

    return judge, calls


def test_judge_not_called_when_the_grader_says_right():
    judge, calls = fake_judge(correct=False)
    result, _, _ = play([FRANCE, SPAIN], ["Pariss", "Madrid"], judge=judge)
    assert calls == []  # exact match and typo-forgiven both skip the judge
    assert result.correct == 2
    assert [a.verdict for a in result.attempts] == [None, None]


@pytest.mark.parametrize("typed", ["", "   "])
def test_judge_not_called_for_a_blank_answer(typed):
    judge, calls = fake_judge(correct=True)
    result, _, _ = play([FRANCE], [typed], judge=judge)
    assert calls == []
    assert result.correct == 0
    assert result.attempts[0].verdict is None
    assert result.attempts[0].correct is False


def test_judge_called_with_question_and_typed_text_when_grader_says_wrong():
    judge, calls = fake_judge(correct=False)
    play([FRANCE], ["  Lutetia "], judge=judge)
    assert calls == [(FRANCE, "  Lutetia ")]


def test_judge_yes_counts_in_the_score():
    judge, _ = fake_judge(correct=True, reason="Old name for Paris.")
    result, _, told = play([FRANCE, ITALY], ["Lutetia", "Rome"], judge=judge)
    attempt = result.attempts[0]
    assert attempt.grade.correct is False  # the grader itself is unchanged
    assert attempt.verdict.correct is True
    assert attempt.verdict.reason == "Old name for Paris."
    assert attempt.correct is True
    assert result.correct == 2
    assert told[0].verdict == attempt.verdict  # tell sees the verdict


def test_judge_no_stays_wrong():
    judge, _ = fake_judge(correct=False, reason="Different city.")
    result, _, _ = play([FRANCE], ["Lyon"], judge=judge)
    attempt = result.attempts[0]
    assert attempt.verdict.correct is False
    assert attempt.correct is False
    assert result.correct == 0


def test_no_judge_is_the_old_behaviour():
    result, _, _ = play(CAPITALS, ["Paris", "Lisbon", "Madrid"])
    assert [a.verdict for a in result.attempts] == [None, None, None]
    assert [a.correct for a in result.attempts] == [True, False, True]
    assert result.correct == 2


def test_attempt_correct_follows_the_grade_without_a_verdict():
    result, _, _ = play([FRANCE, ITALY], ["Pariss", "Lisbon"], judge=None)
    assert [a.correct for a in result.attempts] == [True, False]


def test_session_takes_a_judge_too():
    judge, calls = fake_judge(correct=True)
    session = block.QuizSession([FRANCE, ITALY], judge=judge)
    first = session.answer("Lutetia")
    assert first.correct is True and first.verdict is not None
    second = session.answer("Rome")
    assert second.verdict is None
    assert len(calls) == 1
    assert session.result().correct == 2


def test_ctrl_c_while_the_judge_is_asked_is_a_quit():
    def judge(question, typed):
        raise KeyboardInterrupt

    ask, asked = fake_ask(["Paris", "Lyon", "Madrid"])
    tell, told = collector()
    result = run_expecting_no_ctrl_c(CAPITALS, ask, tell, judge=judge)
    assert result.answered == 1  # answer 1 kept; answer 2 (being judged) doesn't count
    assert result.finished is False
    assert asked == [FRANCE, ITALY]  # ask not called again
    assert told == list(result.attempts)


def test_other_judge_errors_are_passed_through():
    def judge(question, typed):
        raise ValueError("broken judge")

    ask, _ = fake_ask(["Rome"])
    tell, told = collector()
    with pytest.raises(ValueError, match="broken judge"):
        block.run_quiz([FRANCE], ask, tell, judge=judge)
    assert told == []


# -- The prepare hook (ADR 0012) and QuizResult.skipped ----------------------------


def live(question: Question, *answers: str) -> Question:
    """A "prepared" version of `question`: same card, new content and answers."""
    return Question(
        card_id=question.card_id,
        mode="capital_live",
        shown={"country": question.shown["country"], "hint": "old name"},
        accepted_answers=list(answers),
    )


def fake_prepare(replace: dict | None = None):
    """A `prepare` that records each call; `replace` maps card_id -> what to return.

    Cards not in `replace` come back unchanged. A value of None skips that card.
    """
    replace = replace or {}
    calls: list[Question] = []

    def prepare(question: Question) -> Question | None:
        calls.append(question)
        return replace.get(question.card_id, question)

    return prepare, calls


def test_prepare_called_once_per_question_in_order_with_the_question_as_given():
    prepare, calls = fake_prepare()
    result, asked, _ = play(CAPITALS, ["Paris", "Rome", "Madrid"], prepare=prepare)
    assert calls == CAPITALS
    assert asked == CAPITALS
    assert result.correct == 3


def test_prepare_called_only_when_the_question_becomes_current():
    """Not all up front, and not again on a second read of `current`."""
    prepare, calls = fake_prepare()
    session = block.QuizSession(CAPITALS, prepare=prepare)
    assert calls == []  # nothing is prepared when the session is made
    assert session.current == FRANCE
    assert session.current == FRANCE
    assert calls == [FRANCE]
    session.answer("Paris")
    assert session.current == ITALY
    assert session.current == ITALY
    assert calls == [FRANCE, ITALY]


def test_prepared_question_is_what_ask_grader_and_attempt_see():
    old_paris = live(FRANCE, "Lutetia")
    prepare, _ = fake_prepare({"france": old_paris})
    result, asked, told = play([FRANCE, ITALY], ["Lutetia", "Rome"], prepare=prepare)
    assert asked == [old_paris, ITALY]
    assert result.attempts[0].question == old_paris
    assert result.attempts[0].grade.correct is True  # graded against the new answers
    assert told[0].question == old_paris


def test_prepared_question_replaces_the_original_answers():
    prepare, _ = fake_prepare({"france": live(FRANCE, "Lutetia")})
    result, _, _ = play([FRANCE], ["Paris"], prepare=prepare)
    assert result.attempts[0].grade.correct is False


def test_judge_sees_the_prepared_question():
    old_paris = live(FRANCE, "Lutetia")
    prepare, _ = fake_prepare({"france": old_paris})
    judge, calls = fake_judge(correct=False)
    play([FRANCE], ["Paris"], prepare=prepare, judge=judge)
    assert calls == [(old_paris, "Paris")]


def test_prepare_none_skips_the_question():
    prepare, calls = fake_prepare({"italy": None})
    result, asked, told = play(CAPITALS, ["Paris", "Madrid"], prepare=prepare)
    assert calls == CAPITALS
    assert asked == [FRANCE, SPAIN]  # ask not called for the skipped one
    assert [a.question for a in result.attempts] == [FRANCE, SPAIN]
    assert len(told) == 2
    assert (result.correct, result.answered, result.total) == (2, 2, 3)
    assert result.skipped == 1
    assert result.finished is True


def test_skipping_the_last_questions_finishes_the_quiz():
    prepare, _ = fake_prepare({"italy": None, "spain": None})
    session = block.QuizSession(CAPITALS, prepare=prepare)
    assert session.current == FRANCE
    session.answer("Paris")
    assert session.current is None
    assert session.done is True
    result = session.result()
    assert (result.answered, result.skipped, result.total) == (1, 2, 3)
    assert result.finished is True


def test_every_question_skipped_asks_nothing_and_finishes():
    prepare, _ = fake_prepare({"france": None, "italy": None, "spain": None})
    result, asked, told = play(CAPITALS, [], prepare=prepare)
    assert asked == [] and told == []
    assert (result.answered, result.skipped, result.total) == (0, 3, 3)
    assert result.correct == 0
    assert result.finished is True


def test_prepare_returning_another_card_raises_value_error_and_keeps_answers():
    prepare, _ = fake_prepare({"italy": SPAIN})  # wrong card_id for Italy
    session = block.QuizSession(CAPITALS, prepare=prepare)
    assert session.current == FRANCE
    session.answer("Paris")  # marking never prepares the next question
    with pytest.raises(ValueError):
        session.current  # noqa: B018 Italy is prepared (and fails) here
    result = session.result()
    assert result.answered == 1
    assert result.attempts[0].typed == "Paris"


def test_prepare_returning_another_card_raises_in_run_quiz():
    prepare, _ = fake_prepare({"italy": SPAIN})
    ask, asked = fake_ask(["Paris", "Rome", "Madrid"])
    tell, _ = collector()
    with pytest.raises(ValueError):
        block.run_quiz(CAPITALS, ask, tell, prepare=prepare)
    assert asked == [FRANCE]  # Italy was never asked


def test_prepare_returning_an_unanswerable_question_raises_value_error():
    prepare, _ = fake_prepare({"italy": live(ITALY, "   ")})
    ask, asked = fake_ask(["Paris", "Rome", "Madrid"])
    tell, _ = collector()
    with pytest.raises(ValueError):
        block.run_quiz(CAPITALS, ask, tell, prepare=prepare)
    assert asked == [FRANCE]


def test_unanswerable_prepared_question_keeps_the_answers_given():
    prepare, _ = fake_prepare({"italy": live(ITALY, "   ")})
    session = block.QuizSession(CAPITALS, prepare=prepare)
    session.answer("Paris")
    with pytest.raises(ValueError):
        session.current  # noqa: B018
    assert [a.typed for a in session.result().attempts] == ["Paris"]


def test_answer_before_reading_current_prepares_first():
    prepare, _ = fake_prepare({"france": live(FRANCE, "Lutetia")})
    session = block.QuizSession(CAPITALS, prepare=prepare)
    attempt = session.answer("Lutetia")  # current never read
    assert attempt.correct
    assert attempt.question.accepted_answers == ["Lutetia"]


def test_reading_done_prepares_the_current_question():
    prepare, _ = fake_prepare({"france": None, "italy": None, "spain": None})
    session = block.QuizSession(CAPITALS, prepare=prepare)
    assert session.done is True  # all skipped: done had to prepare them
    assert session.result().skipped == 3


def test_ctrl_c_inside_prepare_is_a_quit():
    def prepare(question: Question) -> Question | None:
        if question.card_id == "italy":
            raise KeyboardInterrupt
        return question

    ask, asked = fake_ask(["Paris", "Rome", "Madrid"])
    tell, told = collector()
    result = run_expecting_no_ctrl_c(CAPITALS, ask, tell, prepare=prepare)
    assert (result.correct, result.answered, result.total) == (1, 1, 3)
    assert result.skipped == 0  # the question being prepared isn't skipped
    assert result.finished is False
    assert asked == [FRANCE]
    assert told == list(result.attempts)


def test_other_prepare_errors_are_passed_through():
    def prepare(question: Question) -> Question | None:
        if question.card_id == "italy":
            raise RuntimeError("broken prepare")
        return question

    ask, _ = fake_ask(["Paris", "Rome", "Madrid"])
    tell, _ = collector()
    with pytest.raises(RuntimeError, match="broken prepare"):
        block.run_quiz(CAPITALS, ask, tell, prepare=prepare)


def test_no_prepare_is_the_old_behaviour():
    result, asked, _ = play(CAPITALS, ["Paris", "Lisbon", "Madrid"])
    assert asked == CAPITALS
    assert result.skipped == 0
    assert result.finished is True


def test_session_takes_a_prepare_too():
    old_paris = live(FRANCE, "Lutetia")
    prepare, calls = fake_prepare({"france": old_paris, "italy": None})
    session = block.QuizSession(CAPITALS, prepare=prepare)
    assert session.current == old_paris
    assert session.answer("Lutetia").correct is True
    assert session.current == SPAIN
    session.answer("Madrid")
    assert session.done is True
    result = session.result()
    assert (result.correct, result.answered, result.skipped) == (2, 2, 1)
    assert result.finished is True
    assert calls == CAPITALS


def test_result_skipped_defaults_to_zero():
    assert block.QuizResult(attempts=(), total=2).skipped == 0


def test_result_finished_counts_skipped():
    result, _, _ = play([FRANCE], ["Paris"])
    done = block.QuizResult(attempts=result.attempts, total=3, skipped=2)
    assert done.finished is True
    partway = block.QuizResult(attempts=result.attempts, total=3, skipped=1)
    assert partway.finished is False


def test_result_rejects_answered_plus_skipped_above_total():
    result, _, _ = play([FRANCE], ["Paris"])
    with pytest.raises(ValidationError):
        block.QuizResult(attempts=result.attempts, total=2, skipped=2)


def test_result_rejects_negative_skipped():
    with pytest.raises(ValidationError):
        block.QuizResult(attempts=(), total=1, skipped=-1)


def test_prepare_is_not_called_at_creation_or_after_marking():
    """Lazy: nothing is prepared at creation or after marking, so Ctrl-C or an error is a quit or
    loud in the loop, never while the session is made or an answer is being kept."""
    calls = []

    def prepare(q):
        calls.append(q.card_id)
        return q

    questions = [
        Question(card_id=c, mode="m", shown={"country": c}, accepted_answers=[c])
        for c in ("a", "b")
    ]
    session = block.QuizSession(questions, prepare=prepare)
    assert calls == []
    assert session.current is not None
    session.answer("a")
    assert calls == ["a"]
    assert session.current is not None
    assert calls == ["a", "b"]


def test_prepare_returning_a_non_question_raises_value_error():
    session = block.QuizSession(CAPITALS, prepare=lambda q: "Paris")
    with pytest.raises(ValueError):
        session.current  # noqa: B018


def test_unusable_prepare_result_is_not_asked_for_again():
    """A second read repeats the error without calling prepare (and its side effects)."""
    prepare, calls = fake_prepare({"france": SPAIN})
    session = block.QuizSession(CAPITALS, prepare=prepare)
    for _ in range(2):
        with pytest.raises(ValueError):
            session.current  # noqa: B018
    assert calls == [FRANCE]


# -- Your own mark after the answer (ADR 0014) -------------------------------------


def verdict(correct: bool, source: str = "self", reason: str = "My own mark."):
    from quizkit.models import Verdict

    return Verdict(correct=correct, reason=reason, source=source)


def judge_returning(source: str, correct: bool = False):
    """A judge that always returns a verdict from `source` (e.g. "not_checked")."""

    def judge(question: Question, typed: str):
        return verdict(correct, source=source, reason=f"From {source}.")

    return judge


def test_wrong_answer_without_judge_can_take_own_mark():
    session = block.QuizSession([FRANCE, ITALY])
    session.answer("Lutetia")
    assert session.can_own_mark is True


def test_own_mark_yes_makes_the_answer_count():
    session = block.QuizSession([FRANCE, ITALY])
    session.answer("Lutetia")
    mine = verdict(True)
    attempt = session.own_mark(mine)
    assert isinstance(attempt, block.Attempt)
    assert attempt.verdict == mine
    assert attempt.correct is True
    assert attempt.grade.correct is False  # the grader's verdict is unchanged
    assert attempt.typed == "Lutetia" and attempt.question == FRANCE
    result = session.result()
    assert result.attempts[-1] == attempt
    assert result.correct == 1


def test_own_mark_no_stays_wrong_but_is_marked():
    session = block.QuizSession([FRANCE, ITALY])
    session.answer("Lyon")
    mine = verdict(False)
    attempt = session.own_mark(mine)
    assert attempt.verdict == mine
    assert attempt.correct is False
    assert session.result().correct == 0
    assert session.result().attempts[0].verdict == mine


def test_own_mark_works_after_a_couldnt_check_verdict():
    session = block.QuizSession([FRANCE, ITALY], judge=judge_returning("not_checked"))
    first = session.answer("Lutetia")
    assert first.verdict.source == "not_checked"
    assert session.can_own_mark is True
    attempt = session.own_mark(verdict(True))
    assert attempt.verdict.source == "self"
    assert session.result().correct == 1


def test_own_mark_works_on_the_last_question():
    session = block.QuizSession([FRANCE])
    session.answer("Lutetia")
    assert session.done is True
    assert session.can_own_mark is True
    session.own_mark(verdict(True))
    result = session.result()
    assert result.finished is True
    assert result.correct == 1


def test_own_mark_before_any_answer_raises_runtime_error():
    session = block.QuizSession(CAPITALS)
    assert session.can_own_mark is False
    with pytest.raises(RuntimeError):
        session.own_mark(verdict(True))


@pytest.mark.parametrize("typed", ["Paris", "Pariss"])
def test_own_mark_after_a_right_answer_raises_value_error(typed):
    """Right by the answer list (exact or typo-forgiven): nothing to mark."""
    session = block.QuizSession([FRANCE, ITALY])
    session.answer(typed)
    assert session.can_own_mark is False
    with pytest.raises(ValueError):
        session.own_mark(verdict(True))


@pytest.mark.parametrize("source", ["claude", "cache"])
@pytest.mark.parametrize("judged_correct", [True, False])
def test_own_mark_after_a_checked_verdict_raises_value_error(source, judged_correct):
    session = block.QuizSession(
        [FRANCE, ITALY], judge=judge_returning(source, correct=judged_correct)
    )
    session.answer("Lutetia")
    assert session.can_own_mark is False
    with pytest.raises(ValueError):
        session.own_mark(verdict(True))
    assert session.result().attempts[0].verdict.source == source  # unchanged


def test_own_mark_only_once():
    session = block.QuizSession([FRANCE, ITALY])
    session.answer("Lutetia")
    session.own_mark(verdict(False))
    assert session.can_own_mark is False
    with pytest.raises(ValueError):
        session.own_mark(verdict(True))
    assert session.result().correct == 0  # the first own mark stands


def test_own_mark_after_a_self_verdict_from_the_judge_raises_value_error():
    """The terminal's prompt inside the judge already gave a self mark: that's checked."""
    session = block.QuizSession([FRANCE, ITALY], judge=judge_returning("self"))
    session.answer("Lutetia")
    assert session.can_own_mark is False
    with pytest.raises(ValueError):
        session.own_mark(verdict(True))


@pytest.mark.parametrize("source", ["claude", "cache", "not_checked"])
def test_own_mark_with_a_non_self_verdict_raises_value_error(source):
    session = block.QuizSession([FRANCE, ITALY])
    session.answer("Lutetia")
    with pytest.raises(ValueError):
        session.own_mark(verdict(False, source=source))
    assert session.result().attempts[0].verdict is None  # nothing changed
    assert session.can_own_mark is True  # still waiting for a real own mark


def test_own_mark_changes_only_the_last_answer():
    session = block.QuizSession(CAPITALS)
    session.answer("Lyon")
    session.answer("Milan")
    session.own_mark(verdict(True))
    first, second = session.result().attempts
    assert first.verdict is None and first.correct is False
    assert second.verdict.source == "self" and second.correct is True
    assert session.result().correct == 1


def test_earlier_wrong_answer_cannot_be_marked_after_the_next_answer():
    """Only the last answer: a right answer 2 closes the chance to mark answer 1."""
    session = block.QuizSession(CAPITALS)
    session.answer("Lyon")
    session.answer("Rome")
    assert session.can_own_mark is False
    with pytest.raises(ValueError):
        session.own_mark(verdict(True))
    assert session.result().attempts[0].verdict is None


def test_own_mark_does_not_move_the_quiz_on():
    session = block.QuizSession(CAPITALS)
    session.answer("Lyon")
    session.own_mark(verdict(True))
    assert session.current == ITALY
    assert session.result().answered == 1


@pytest.mark.parametrize("typed", ["", "   "])
def test_blank_answer_cannot_take_own_mark(typed):
    session = block.QuizSession([FRANCE, ITALY])
    session.answer(typed)
    assert session.can_own_mark is False
    with pytest.raises(ValueError):
        session.own_mark(verdict(True))


def test_own_mark_when_every_question_so_far_was_skipped_raises_runtime_error():
    prepare, _ = fake_prepare({"france": None})
    session = block.QuizSession(CAPITALS, prepare=prepare)
    assert session.current == ITALY  # France skipped, nothing answered yet
    assert session.can_own_mark is False
    with pytest.raises(RuntimeError):
        session.own_mark(verdict(True))


def test_own_mark_with_something_that_is_not_a_verdict_raises_type_error():
    session = block.QuizSession([FRANCE])
    session.answer("Lyon")
    with pytest.raises(TypeError):
        session.own_mark({"correct": True, "reason": "yes", "source": "self"})
    assert session.can_own_mark is True  # nothing changed


def test_own_mark_for_another_card_raises_and_changes_nothing():
    """A late click meant for France must not land on Italy (code review)."""
    from quizkit.models import Verdict

    session = block.QuizSession([FRANCE, ITALY])
    session.answer("Lyon")
    session.answer("Milan")
    yes = Verdict(correct=True, reason="yes", source="self")
    with pytest.raises(ValueError):
        session.own_mark(yes, card_id=FRANCE.card_id)
    assert session.result().correct == 0
    assert session.own_mark(yes, card_id=ITALY.card_id).correct is True
