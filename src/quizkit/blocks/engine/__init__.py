"""engine: Run a quiz: show each question, mark the typed answer with the grader, and keep score.

See SPEC.md in this folder (ADR 0003). Two layers:
- `QuizSession` (the brain): step by step, no keyboard or screen code (fits a web UI).
- `run_quiz` (the voice): the whole loop, getting answers from `ask`, feedback to `tell`.
Generic: it never imports deck_builder or anything quiz-specific. An optional `prepare`
finishes each question just before it is asked, or skips it (ADR 0012).
"""

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from quizkit.blocks.base import BlockSpec
from quizkit.blocks.grader import Grade, GradeSettings, grade
from quizkit.models import Judge, Question, Verdict

BLOCK_SPEC = BlockSpec(
    name="engine",
    kind="script",
    goal="Run a quiz: show each question, mark the typed answer with the grader, and keep score.",
    inputs=["questions", "settings", "ask", "tell", "judge", "prepare"],
    outputs=["Attempt", "QuizResult"],
)


class Attempt(BaseModel):
    """One answered question: what was asked, what was typed, and the verdicts."""

    model_config = ConfigDict(frozen=True)

    question: Question
    typed: str
    grade: Grade
    # The judge's (only asked when the grader said wrong), or your own mark (own_mark)
    verdict: Verdict | None = None

    @computed_field
    @property
    def correct(self) -> bool:
        """Right by the answer list (typos forgiven), or the judge (or your own
        mark) said yes."""
        return self.grade.correct or (self.verdict is not None and self.verdict.correct)


class QuizResult(BaseModel):
    """The whole quiz so far: every attempt in order, plus the score."""

    model_config = ConfigDict(frozen=True)

    attempts: tuple[Attempt, ...]  # a tuple, so a frozen result truly can't change
    total: int = Field(ge=1)
    skipped: int = Field(default=0, ge=0)  # questions `prepare` skipped

    @model_validator(mode="after")
    def total_covers_attempts(self) -> "QuizResult":
        if len(self.attempts) + self.skipped > self.total:
            raise ValueError(
                f"{len(self.attempts)} attempts and {self.skipped} skipped, but the quiz "
                f"only has {self.total} questions"
            )
        return self

    @computed_field
    @property
    def correct(self) -> int:
        return sum(a.correct for a in self.attempts)  # typo-forgiven and judged count

    @computed_field
    @property
    def answered(self) -> int:
        return len(self.attempts)

    @computed_field
    @property
    def finished(self) -> bool:
        return self.answered + self.skipped == self.total


class QuizSession:
    """The brain: which question is next, mark an answer, keep score."""

    def __init__(
        self,
        questions: list[Question],
        settings: GradeSettings | None = None,
        judge: Judge | None = None,
        prepare: Callable[[Question], Question | None] | None = None,
    ) -> None:
        if not questions:
            raise ValueError("a quiz needs at least one question")
        # Own deep copy: later changes to the caller's list *or its questions* don't leak in.
        self._questions = [q.model_copy(deep=True) for q in questions]
        self._settings = settings or GradeSettings()
        self._judge = judge
        self._prepare = prepare
        self._attempts: list[Attempt] = []
        self._skipped = 0
        self._ready: Question | None = None  # the prepared current question
        self._bad: ValueError | None = None  # what prepare returned was unusable
        # Fail before question 1, not mid-quiz: a card nobody can answer makes the
        # grader raise, so grade a blank answer for each one now.
        for question in self._questions:
            grade("", question.accepted_answers, settings=self._settings)

    @property
    def current(self) -> Question | None:
        """The question being asked now (prepared), or None when the quiz is finished.

        With `prepare`, each question is prepared once, the first time it is current;
        a skipped one is counted and the next is prepared.
        """
        if self._bad is not None:  # don't call prepare (and its side effects) again
            raise self._bad
        # One counter of truth: the next question is the one after those done.
        while self._ready is None and (at := len(self._attempts) + self._skipped) < len(
            self._questions
        ):
            given = self._questions[at]
            if self._prepare is None:
                self._ready = given
                break
            offered = given.model_copy(deep=True)  # prepare can't change ours
            prepared = self._prepare(offered)
            if prepared is None:
                self._skipped += 1
                continue
            self._ready = self._usable(prepared, given, offered)
        return self._ready

    def _usable(self, prepared: object, given: Question, offered: Question) -> Question:
        """Check what prepare returned; an unusable one stays an error (loud)."""
        try:
            if not isinstance(prepared, Question):
                raise ValueError(  # noqa: TRY004 (SPEC: every bad prepare result is a ValueError)
                    f"prepare must return a Question or None, not {type(prepared).__name__}"
                )
            if prepared.card_id != given.card_id:
                raise ValueError(
                    f"prepare returned a question for {prepared.card_id!r}, "
                    f"not {given.card_id!r}"
                )
            grade("", prepared.accepted_answers, settings=self._settings)
        except ValueError as err:
            self._bad = err
            raise
        # A new object from prepare may still be held by it: keep our own copy.
        return prepared if prepared is offered else prepared.model_copy(deep=True)

    @property
    def done(self) -> bool:
        return self.current is None

    def answer(self, typed: str) -> Attempt:
        """Mark `typed` for the current question, move on, and return the Attempt."""
        question = self.current
        if question is None:
            raise RuntimeError("the quiz is finished: there is no question to answer")
        marked = grade(typed, question.accepted_answers, settings=self._settings)
        verdict = None
        if _checkable(marked, typed) and self._judge is not None:
            verdict = self._judge(question, typed)  # only when the list says wrong
        attempt = Attempt(question=question, typed=typed, grade=marked, verdict=verdict)
        self._attempts.append(attempt)
        self._ready = None
        return attempt

    @property
    def can_own_mark(self) -> bool:
        """True if the last answer is waiting for your own mark (ADR 0014): typed,
        wrong by the answer list, and nobody checked it (no verdict, or "couldn't
        check")."""
        return bool(self._attempts) and _markable(self._attempts[-1])

    def own_mark(self, verdict: Verdict, card_id: str | None = None) -> Attempt:
        """Your own mark on the last answer (e.g. "Did you get the gist?"), given
        after `answer()` because a web page can't pause inside it. Returns the
        updated Attempt; the quiz doesn't move on. Pass the `card_id` the mark is
        for, so a late or repeated click can't land on a later answer."""
        if not self._attempts:
            raise RuntimeError("there is no answer yet to mark")
        if not isinstance(verdict, Verdict):
            raise TypeError(f"own_mark takes a Verdict, not {type(verdict).__name__}")
        if verdict.source != "self":
            raise ValueError(
                f"own_mark takes your own mark (source 'self'), not {verdict.source!r}"
            )
        last = self._attempts[-1]
        if card_id is not None and card_id != last.question.card_id:
            raise ValueError(
                f"the mark is for {card_id!r}, but the last answer was for "
                f"{last.question.card_id!r}"
            )
        if not _markable(last):
            raise ValueError(
                "the last answer can't take your mark: it was blank, right by the "
                "answer list, or already checked"
            )
        # A new Attempt (validated), not model_copy: the record stays trustworthy.
        marked = Attempt(
            question=last.question, typed=last.typed, grade=last.grade, verdict=verdict
        )
        self._attempts[-1] = marked
        return marked

    def result(self) -> QuizResult:
        return QuizResult(
            attempts=tuple(self._attempts),
            total=len(self._questions),
            skipped=self._skipped,
        )


def _checkable(marked: Grade, typed: str) -> bool:
    """Worth a second look (the judge's, or your own mark): wrong by the answer list,
    and something was typed. One rule for both, so they never disagree."""
    return not marked.correct and bool(typed.strip())


def _markable(attempt: Attempt) -> bool:
    """Can take your own mark: checkable, and nobody checked it yet."""
    return _checkable(attempt.grade, attempt.typed) and (
        attempt.verdict is None or attempt.verdict.source == "not_checked"
    )


def run_quiz(
    questions: list[Question],
    ask: Callable[[Question], str | None],
    tell: Callable[[Attempt], None],
    settings: GradeSettings | None = None,
    judge: Judge | None = None,
    prepare: Callable[[Question], Question | None] | None = None,
) -> QuizResult:
    """The voice: ask every question in turn; `ask` returning None means quit.

    Ctrl-C (KeyboardInterrupt) anywhere in the loop is a quit too: on Windows it can
    land just after input() returns, while grading or in `tell`, not only in `ask`;
    and inside `prepare` (e.g. waiting for a live sentence).
    """
    session = QuizSession(questions, settings=settings, judge=judge, prepare=prepare)
    try:
        while (question := session.current) is not None:
            typed = ask(question)
            if typed is None:
                break
            tell(session.answer(typed))
    except KeyboardInterrupt:
        pass  # keep the score so far
    return session.result()
