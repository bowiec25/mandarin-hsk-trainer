"""engine: Run a quiz: show each question, mark the typed answer with the grader, and keep score.

See SPEC.md in this folder (ADR 0003). Two layers:
- `QuizSession` (the brain): step by step, no keyboard or screen code (fits a web UI).
- `run_quiz` (the voice): the whole loop, getting answers from `ask`, feedback to `tell`.
Generic: it never imports deck_builder or anything quiz-specific.
"""

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from quizkit.blocks.base import BlockSpec
from quizkit.blocks.grader import Grade, GradeSettings, grade
from quizkit.models import Question

BLOCK_SPEC = BlockSpec(
    name="engine",
    kind="script",
    goal="Run a quiz: show each question, mark the typed answer with the grader, and keep score.",
    inputs=["questions", "settings", "ask", "tell"],
    outputs=["Attempt", "QuizResult"],
)


class Attempt(BaseModel):
    """One answered question: what was asked, what was typed, and the grader's verdict."""

    model_config = ConfigDict(frozen=True)

    question: Question
    typed: str
    grade: Grade


class QuizResult(BaseModel):
    """The whole quiz so far: every attempt in order, plus the score."""

    model_config = ConfigDict(frozen=True)

    attempts: tuple[Attempt, ...]  # a tuple, so a frozen result truly can't change
    total: int = Field(ge=1)

    @model_validator(mode="after")
    def total_covers_attempts(self) -> "QuizResult":
        if len(self.attempts) > self.total:
            raise ValueError(
                f"{len(self.attempts)} attempts but the quiz only has {self.total} questions"
            )
        return self

    @computed_field
    @property
    def correct(self) -> int:
        return sum(a.grade.correct for a in self.attempts)  # typo-forgiven counts

    @computed_field
    @property
    def answered(self) -> int:
        return len(self.attempts)

    @computed_field
    @property
    def finished(self) -> bool:
        return self.answered == self.total


class QuizSession:
    """The brain: which question is next, mark an answer, keep score."""

    def __init__(
        self,
        questions: list[Question],
        settings: GradeSettings | None = None,
    ) -> None:
        if not questions:
            raise ValueError("a quiz needs at least one question")
        # Own deep copy: later changes to the caller's list *or its questions* don't leak in.
        self._questions = [q.model_copy(deep=True) for q in questions]
        self._settings = settings or GradeSettings()
        self._attempts: list[Attempt] = []
        # Fail before question 1, not mid-quiz: a card nobody can answer makes the
        # grader raise, so grade a blank answer for each one now.
        for question in self._questions:
            grade("", question.accepted_answers, settings=self._settings)

    @property
    def current(self) -> Question | None:
        """The question being asked now, or None when the quiz is finished."""
        if self.done:
            return None
        return self._questions[len(self._attempts)]

    @property
    def done(self) -> bool:
        return len(self._attempts) == len(self._questions)

    def answer(self, typed: str) -> Attempt:
        """Mark `typed` for the current question, move on, and return the Attempt."""
        question = self.current
        if question is None:
            raise RuntimeError("the quiz is finished: there is no question to answer")
        verdict = grade(typed, question.accepted_answers, settings=self._settings)
        attempt = Attempt(question=question, typed=typed, grade=verdict)
        self._attempts.append(attempt)
        return attempt

    def result(self) -> QuizResult:
        return QuizResult(attempts=tuple(self._attempts), total=len(self._questions))


def run_quiz(
    questions: list[Question],
    ask: Callable[[Question], str | None],
    tell: Callable[[Attempt], None],
    settings: GradeSettings | None = None,
) -> QuizResult:
    """The voice: ask every question in turn; `ask` returning None means quit.

    Ctrl-C (KeyboardInterrupt) anywhere in the loop is a quit too: on Windows it can
    land just after input() returns, while grading or in `tell`, not only in `ask`.
    """
    session = QuizSession(questions, settings=settings)
    try:
        while (question := session.current) is not None:
            typed = ask(question)
            if typed is None:
                break
            tell(session.answer(typed))
    except KeyboardInterrupt:
        pass  # keep the score so far
    return session.result()
