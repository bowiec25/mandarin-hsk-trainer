"""Tests for the engine block: contract (ID card + SPEC) and behaviour (from SPEC.md)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

import quizkit.blocks.engine as block
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


# -- cleaner and settings are passed straight to the grader ------------------------


def toy_cleaner(answer: str) -> list[str]:
    """'Paris' also accepts its old name 'Lutetia'."""
    return [answer, "Lutetia"] if answer == "Paris" else [answer]


def test_cleaner_is_passed_to_grader():
    without, _, _ = play([FRANCE], ["Lutetia"])
    with_cleaner, _, _ = play([FRANCE], ["Lutetia"], cleaner=toy_cleaner)
    assert without.correct == 0
    assert with_cleaner.correct == 1


def test_settings_are_passed_to_grader():
    result, _, _ = play([FRANCE], ["Pariss"], settings=GradeSettings(allow_typos=False))
    assert result.correct == 0


def test_session_passes_cleaner_and_settings():
    session = block.QuizSession(
        [FRANCE, FRANCE],
        cleaner=toy_cleaner,
        settings=GradeSettings(allow_typos=False),
    )
    assert session.answer("Lutetia").grade.correct is True
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


def test_session_defaults_work_without_cleaner_or_settings():
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
    def ask(question: Question) -> str | None:
        raise KeyboardInterrupt

    tell, _ = collector()
    with pytest.raises(KeyboardInterrupt):
        block.run_quiz(CAPITALS, ask, tell)


def test_error_from_tell_is_passed_through():
    ask, _ = fake_ask(["Paris"])

    def tell(attempt) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        block.run_quiz(CAPITALS, ask, tell)


def test_grader_error_is_passed_through():
    """A card nobody can answer is a data bug: the grader's error must surface."""
    unanswerable = q("Nowhere", "   ")
    with pytest.raises(ValueError):
        play([unanswerable], ["anything"])


def test_broken_cleaner_error_is_passed_through():
    def broken(answer: str) -> list[str]:
        return "not a list"  # type: ignore[return-value]

    ask, asked = fake_ask(["Paris"])
    tell, _ = collector()
    with pytest.raises(TypeError):
        block.run_quiz([FRANCE], ask, tell, cleaner=broken)
    assert asked == []  # found before question 1


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


def test_changing_a_question_after_starting_has_no_effect():
    france = q("France", "Paris")
    session = block.QuizSession([france])
    france.accepted_answers.append("Lyon")  # the list inside a frozen model can change
    assert session.answer("Lyon").grade.correct is False
