"""The web quiz's brain: which screen to show, and what each click does (ADR 0014).

No Streamlit in here, so it can be tested like any Python. The page (`web_app.py`)
reruns its whole script on every click; this object survives between runs (kept in
the page's session state) and is the only thing that moves the quiz on.

Phases: setup -> asking -> result | own_mark -> ... -> ended. A click that arrives in
the wrong phase, or for a question that's gone (a double click, a late click), is
ignored. Drawing the page only reads `view` / `result` / `marking` / `summary`:
reading them never moves the quiz on, fetches a sentence or writes a file.
"""

from dataclasses import dataclass, field
from typing import Literal

from hsk_trainer.quiz_setup import (
    GIST_QUESTION,
    GOT_THE_GIST,
    MISSED_IT,
    HskQuiz,
    QuizFiles,
    QuizOptions,
    SetupError,
    build_quiz,
    describe,
    end_lines,
    unmarked,
)
from quizkit.blocks.engine import Attempt, QuizSession
from quizkit.blocks.judge import ClaudeJudge
from quizkit.models import Question

Phase = Literal["setup", "asking", "own_mark", "result", "ended"]
LIVE_HINT = "turn on Live sentences"  # how the page says the terminal's "try --live"


@dataclass(frozen=True)
class QuestionView:
    """One question, frozen when it was reached: what to draw while you answer."""

    card_id: str
    number: int  # 1-based place in the deck (skipped ones count)
    total: int
    translating: bool
    shown: list[str]  # the word (and pinyin), or the sentence in translate modes
    sentence: list[str]  # sentence modes: the example under the word (hanzi, pinyin)
    notes: list[str]  # e.g. "skipped 杯子: no example sentence yet"


@dataclass(frozen=True)
class MarkView:
    """Waiting for your own mark: the English, and why nobody else could check it."""

    card_id: str
    typed: str
    english: str
    question: str = GIST_QUESTION
    why: str | None = None  # e.g. "the judge couldn't check: offline"


@dataclass(frozen=True)
class ResultView:
    """A final answer: what to say about it, and the lines after it."""

    card_id: str
    typed: str
    headline: str  # "✅ ..." or "❌ ..."
    right: bool
    details: list[str]  # the judge's reason
    after: list[str]  # the English, pinyin, the word line
    warning: str | None = None  # couldn't save this answer


@dataclass
class WebQuiz:
    """One quiz in one browser tab. `judge_class` is the judge to build (a fake in
    tests); `files` where everything is (the defaults, or test copies)."""

    judge_class: type[ClaudeJudge] = ClaudeJudge
    files: QuizFiles | None = None
    phase: Phase = "setup"
    problems: list[str] = field(default_factory=list)  # why the last start failed
    intro: list[str] = field(default_factory=list)  # e.g. "Only 3 band-1 words"
    view: QuestionView | None = None
    marking: MarkView | None = None
    result: ResultView | None = None
    summary: list[str] = field(default_factory=list)
    options: QuizOptions | None = None
    _hsk: HskQuiz | None = None
    _session: QuizSession | None = None
    _waiting: Attempt | None = None  # the answer waiting for your own mark
    _notes: list[str] = field(default_factory=list)  # gathered for the next question

    # --- clicks -------------------------------------------------------------------

    def start(self, options: QuizOptions) -> None:
        """Start a quiz (Start button). A setup problem goes to `problems`."""
        if self.phase not in ("setup", "ended"):
            return
        self._reset()
        try:
            hsk = build_quiz(
                options, self.files or QuizFiles(), judge_class=self.judge_class
            )
        except SetupError as err:
            self.problems = list(err.lines)
            return
        self.options, self._hsk = options, hsk
        if len(hsk.questions) < options.n:
            count = len(hsk.questions)
            self.intro.append(
                f"Only {count} band-{options.band} words, so the quiz has {count}."
            )
        prepare = self._translate if hsk.translating and hsk.sentences else None
        self._session = hsk.session(judge=hsk.judge, prepare=prepare)
        if hsk.sentences is not None:
            hsk.sentences.start()
        self._advance()

    def submit(self, typed: str, card_id: str) -> None:
        """Check an answer (Check button / Enter) for the question `card_id`."""
        if self.phase != "asking" or self.view is None or card_id != self.view.card_id:
            return
        attempt = self._quiz.answer(typed)
        if self._hsk_now.translating and self._quiz.can_own_mark:
            self._waiting = attempt
            why = None
            if attempt.verdict is not None:  # the judge was asked but couldn't check
                why = f"the judge couldn't check: {attempt.verdict.reason}"
            self.marking = MarkView(
                card_id=card_id,
                typed=typed,
                english=attempt.question.accepted_answers[0],
                why=why,
            )
            self.phase = "own_mark"
            return
        self._final(attempt)

    def mark(self, got_it: bool, card_id: str) -> None:
        """Your own mark (Yes / No) on the answer waiting for it."""
        if self.phase != "own_mark" or self._waiting is None:
            return
        if card_id != self._waiting.question.card_id:
            return
        verdict = GOT_THE_GIST if got_it else MISSED_IT
        self._final(self._quiz.own_mark(verdict, card_id=card_id))

    def next(self, card_id: str) -> None:
        """Go on from the result of `card_id` (Next button)."""
        if self.phase != "result" or self.result is None:
            return
        if card_id != self.result.card_id:
            return
        self._advance()

    def stop(self) -> None:
        """Stop now (Stop button): the score so far. An answer waiting for your own
        mark is saved "not marked", so its box stays (as in the terminal)."""
        if self.phase not in ("asking", "own_mark", "result"):
            return
        warning = None
        if self.phase == "own_mark" and self._waiting is not None:
            warning = self._save(unmarked(self._waiting))
        self._finish(warning)

    def new_quiz(self) -> None:
        """Back to the settings (New quiz button), after a quiz has ended."""
        if self.phase == "ended":
            self._reset()
            self.phase = "setup"

    # --- inside ---------------------------------------------------------------------

    @property
    def _quiz(self) -> QuizSession:
        assert self._session is not None, "no quiz running"
        return self._session

    @property
    def _hsk_now(self) -> HskQuiz:
        assert self._hsk is not None, "no quiz running"
        return self._hsk

    def _reset(self) -> None:
        self.problems, self.intro, self.summary, self._notes = [], [], [], []
        self.view = self.marking = self.result = None
        self.options = self._hsk = self._session = self._waiting = None

    def _translate(self, question: Question) -> Question | None:
        """The engine's `prepare` in translate modes: the shared one, keeping every
        note (several words in a row can be skipped before the next question)."""
        part = self._hsk_now.sentences
        assert part is not None
        ready = part.translate(question)
        if part.note:
            self._notes.append(part.note)
        if ready is None:
            self._notes.append(f"skipped {part.skipped}: no example sentence yet")
        return ready

    def _advance(self) -> None:
        """Move to the next question, once: the only step that fetches a sentence
        (and marks it seen). The question is frozen into `view`."""
        hsk, session = self._hsk_now, self._quiz
        self.marking = self.result = None
        self._waiting = None
        question = session.current  # translate modes: prepare runs here, once
        if question is None:
            self._finish()
            return
        sentence: list[str] = []
        if hsk.sentences is not None and not hsk.translating:
            part = hsk.sentences
            found = part.fetch(question)
            if part.note:
                self._notes.append(part.note)
            if found is None:
                sentence = ["(no example sentence yet for this word)"]
            else:
                sentence = [found.hanzi]
                if "sentence_pinyin" in part.fields:
                    sentence.append(found.pinyin)
        done = session.result()
        self.view = QuestionView(
            card_id=question.card_id,
            number=done.answered + done.skipped + 1,
            total=done.total,
            translating=hsk.translating,
            shown=list(question.shown.values()),
            sentence=sentence,
            notes=self._notes,
        )
        self._notes = []
        self.phase = "asking"

    def _save(self, attempt: Attempt) -> str | None:
        saver = self._hsk_now.saver
        return saver.save(attempt) if saver is not None else None

    def _final(self, attempt: Attempt) -> None:
        """An answer is final: save it first, then show it."""
        hsk = self._hsk_now
        warning = self._save(attempt)
        headline, details = describe(attempt, hsk.translating)
        after: list[str] = []
        if hsk.sentences is not None:
            if hsk.translating:  # with the English: the mark screen has gone
                after = hsk.sentences.after_translation()
            elif hsk.sentences.current is not None:
                after = [f"= {hsk.sentences.current.english}"]
        self._waiting, self.marking = None, None
        self.result = ResultView(
            card_id=attempt.question.card_id,
            typed=attempt.typed,
            headline=headline,
            right=attempt.correct,
            details=details,
            after=after,
            warning=warning,
        )
        self.phase = "result"

    def _finish(self, warning: str | None = None) -> None:
        hsk, session = self._hsk_now, self._quiz
        notes = list(self._notes)
        if hsk.sentences is not None:
            notes += hsk.sentences.finish()
        assert self.options is not None
        # Notes first (the last skips, late sentences), as the terminal shows them.
        self.summary = [f"({note})" for note in notes]
        self.summary += end_lines(
            session.result(), self.options.live, hsk.saver, live_hint=LIVE_HINT
        )
        if warning:
            self.summary.append(warning)
        self.view = self.marking = self.result = None
        self._waiting, self._notes = None, []
        self.phase = "ended"
