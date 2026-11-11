"""The shared HSK quiz setup: build everything one quiz needs (ADR 0014).

Used by both front ends, the terminal (`cli.py`) and the web page, so neither copies
the other. It prints nothing and reads no keys: notes come back as text, and a setup
problem is a `SetupError` with the lines to show. Glue, not a block (like `cli.py`).
"""

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from hsk_trainer.blocks.answer_writer import ANSWERS_FILE, AnswerFileError, load_answers
from hsk_trainer.blocks.live_sentences import LiveSentences
from hsk_trainer.blocks.sentence_bank import (
    REMOVED_FILE,
    SEEN_FILE,
    RemovedListError,
    SentenceBank,
)
from hsk_trainer.blocks.sentence_writer import (
    SENTENCES_FILE,
    Sentence,
    SentenceFileError,
)
from hsk_trainer.modes import HSK_MODES
from quizkit.blocks.deck_builder import build_deck
from quizkit.blocks.engine import Attempt, QuizResult, QuizSession
from quizkit.blocks.grader import GradeSettings, clean
from quizkit.blocks.judge import GIST_MAX_CHARS, GIST_RUBRIC, ClaudeJudge
from quizkit.blocks.leitner import DEFAULT_RULE
from quizkit.blocks.progress_store import ProgressFileError, ProgressStore
from quizkit.files import load_cards
from quizkit.models import Card, Judge, Question, Verdict
from quizkit.modes import Mode
from quizkit.progress import SkillStats, save_attempt, skill_stats

# Found from this file, so `hsk` works from any folder (src/hsk_trainer/ -> root).
# Assumes it runs from the repo (`uv run hsk`), not from an installed wheel.
ROOT = Path(__file__).resolve().parents[2]
CARDS_FILE = ROOT / "data" / "processed" / "cards.jsonl"
JUDGE_CACHE = ROOT / "data" / "judge_cache.jsonl"  # gitignored: verdicts, not source
PROGRESS_FILE = ROOT / "data" / "progress.db"  # gitignored: your own progress
RULE = DEFAULT_RULE  # the Leitner boxes: the quiz moves cards by it, stats shows it
SETTINGS = GradeSettings()
# Sentences: no typo forgiveness. A 1-2 letter change can flip the meaning
# ("I don't like" -> "I do like"); near-misses go to the gist judge instead.
TRANSLATE_SETTINGS = GradeSettings(allow_typos=False)
# The only HSK part of the judge: what the quiz is about (ADR 0007).
JUDGE_SUBJECT = (
    "Chinese vocabulary for learners of HSK 3.0, bands 1-3. The learner sees a "
    "Chinese word and types its English meaning."
)
# The translate modes' subject; the sentence eval set uses the same one (ADR 0012).
TRANSLATE_SUBJECT = (
    "Chinese example sentences for learners of HSK 3.0, bands 1-3. The learner sees "
    "a Chinese sentence and types what it means in English."
)
PLAYABLE_MODES = tuple(HSK_MODES)
SENTENCE_FIELDS = ("sentence", "sentence_pinyin")  # from the bank, not the card
SHOW_ANSWERS = 4  # how many accepted answers to show after a wrong one

# Your own mark on a translation (ADR 0012): the same words in every front end.
GOT_THE_GIST = Verdict(correct=True, reason="you got the gist", source="self")
MISSED_IT = Verdict(correct=False, reason="you missed it", source="self")
NOT_MARKED = Verdict(correct=False, reason="not marked", source="not_checked")
GIST_QUESTION = "Did you get the gist?"
NO_SENTENCE = "no example sentence yet for this word"


def skip_note(word: str) -> str:
    """The note for a word a translate mode skipped (no usable sentence)."""
    return f"skipped {word}: no example sentence yet"


class _Default(Enum):
    """ "Not given": HskQuiz.session then uses the quiz's own prepare."""

    PREPARE = auto()


class SetupError(Exception):
    """The quiz can't start; `lines` say why and how to fix it, ready to show."""

    def __init__(self, *lines: str) -> None:
        super().__init__("\n".join(lines))
        self.lines = lines


@dataclass(frozen=True)
class QuizOptions:
    band: int = 1
    mode: str = "char"
    n: int = 10
    seed: int | None = None
    judge: bool = True  # ask Claude about answers the list misses
    live: bool = True  # new sentences from Claude as you play
    save: bool = True  # save answers + boxes, deal due words first


@dataclass(frozen=True)
class QuizFiles:
    """Where everything is. Defaults are read when a QuizFiles is made, not at import,
    so tests can point them elsewhere. Your own files (progress, judge cache, seen
    sentences) also follow HSK_PROGRESS_FILE / HSK_JUDGE_CACHE / HSK_SEEN_FILE if set:
    the tests set them, so no test, not even one running the program in a separate
    process, touches the real ones."""

    cards: Path = field(default_factory=lambda: CARDS_FILE)
    answers: Path = field(default_factory=lambda: ANSWERS_FILE)
    sentences: Path = field(default_factory=lambda: SENTENCES_FILE)
    removed: Path = field(default_factory=lambda: REMOVED_FILE)  # ADR 0015
    seen: Path = field(default_factory=lambda: seen_file())
    progress: Path = field(default_factory=lambda: progress_file())
    judge_cache: Path = field(default_factory=lambda: judge_cache_file())


def seen_file() -> Path:
    """When each sentence was last shown: HSK_SEEN_FILE if set (tests), else
    data/sentence_seen.json."""
    return Path(os.environ.get("HSK_SEEN_FILE") or SEEN_FILE)


def progress_file() -> Path:
    """Your progress file: HSK_PROGRESS_FILE if set (tests), else data/progress.db."""
    return Path(os.environ.get("HSK_PROGRESS_FILE") or PROGRESS_FILE)


def judge_cache_file() -> Path:
    """The judge's cache: HSK_JUDGE_CACHE if set (tests), else data/judge_cache.jsonl."""
    return Path(os.environ.get("HSK_JUDGE_CACHE") or JUDGE_CACHE)


def mode_problem(mode: str) -> str | None:
    """Why `mode` can't be played, or None if it can (one message for every front end)."""
    if mode in PLAYABLE_MODES:
        return None
    return f"{mode!r} is not a mode. Try: {', '.join(PLAYABLE_MODES)}."


def readable(question: Question) -> dict[str, str]:
    """Each accepted answer, in the grader's normalised form -> as written for people.

    The grader compares normalised text ("haven't" -> "havent", "to love" -> "love");
    showing that would teach misspellings. Same order and de-duplication as the grader.
    """
    shown: dict[str, str] = {}
    for answer in question.accepted_answers:
        key = clean(answer, SETTINGS)
        if key and key not in shown:
            shown[key] = answer
    return shown


def with_answers(cards: list[Card], answers_file: Path) -> list[Card]:
    """Each card with its answers from answers.jsonl (the one answer list, ADR 0006).

    load_answers checks the file with the writer's own checker; Card re-checks each
    card. Raises ValueError (AnswerFileError is one) for a bad or incomplete file.
    """
    answers = load_answers(answers_file, cards)
    return [
        Card.model_validate({**c.model_dump(), "answers": answers[c.id]}) for c in cards
    ]


def _accepted(verdict: Verdict) -> str:
    """The headline when a verdict said yes: your own mark, or the judge's."""
    if verdict.source == "self":
        return f"✅ {verdict.reason}"
    return f"✅ accepted by the Claude judge: {verdict.reason}"


def _why_not(verdict: Verdict | None, word: bool) -> list[str]:
    """The detail under a wrong answer: the judge's reason, or why nobody checked.
    Nothing for your own "no" (no judge was asked, so don't say "judge")."""
    if verdict is None or verdict.source == "self":
        return []
    if verdict.source == "not_checked":
        return [f"(judge {verdict.reason})" if word else f"({verdict.reason})"]
    return [f"judge: {verdict.reason}"]


def describe(attempt: Attempt, translating: bool) -> tuple[str, list[str]]:
    """What to say about a marked answer: a headline (✅ or ❌ ...) and detail lines
    (the judge's reason). The same words in every front end; each adds its own layout.
    Word modes show the accepted answers after a wrong one; translate modes show the
    English separately (SentencePart.after_translation)."""
    g, verdict = attempt.grade, attempt.verdict
    shown = readable(attempt.question)
    if g.correct and g.typo:
        typo = "✅ close enough (typo)"
        return (
            typo if translating else f"{typo}: {shown.get(g.matched, g.matched)}"
        ), []
    if g.correct:
        return "✅", []
    if verdict is not None and verdict.correct:
        return _accepted(verdict), []
    if translating:
        return "❌", _why_not(verdict, word=False)
    answers = list(shown.values())
    more = " …" if len(answers) > SHOW_ANSWERS else ""
    return f"❌ {'; '.join(answers[:SHOW_ANSWERS])}{more}", _why_not(verdict, word=True)


def unmarked(attempt: Attempt) -> Attempt:
    """The answer, "not marked": for leaving while it waits for your own mark. Saved
    like this, its box stays (nobody checked it), as in the terminal (ADR 0014).
    Only for an answer the list marked wrong: a right one stays right (ValueError).
    A new validated Attempt, as the engine's own_mark makes."""
    if attempt.grade.correct:
        raise ValueError("the answer list already marked this right: nothing to mark")
    return Attempt(
        question=attempt.question,
        typed=attempt.typed,
        grade=attempt.grade,
        verdict=NOT_MARKED,
    )


class SentencePart:
    """The sentence part of a question: shown under the word, or (translate modes)
    the question itself; its English after the answer (ADR 0011, 0012). New ones from
    Claude or banked ones, via live_sentences. Prints nothing: the last note and the
    last skipped word are kept for the front end to show. They (and `revealed`) are
    about the latest question only, so show a result before asking the next one."""

    def __init__(
        self,
        live: LiveSentences,
        fields: list[str],
        questions: list[Question],
        cards: dict[str, Card] | None = None,
    ) -> None:
        self.live = live
        self.fields = fields  # which of SENTENCE_FIELDS the mode shows, in order
        self.questions = questions
        self.cards = cards or {}  # for the word line after a translation
        self.current: Sentence | None = None
        self.revealed = False  # the English was shown already (your own mark)
        self.note: str | None = None  # e.g. "Claude was slow: a banked sentence"
        self.skipped: str | None = None  # the word just skipped (no sentence)
        self.at = 0  # questions shown so far (the engine asks them in turn)

    def start(self) -> None:
        """Before the first question: start on its sentence."""
        if self.questions:
            self.live.prepare(self.questions[0].card_id)

    def fetch(self, question: Question) -> Sentence | None:
        """This question's sentence (`note` says if it wasn't a fresh one)."""
        shown = self.live.sentence_for(question.card_id)
        self.current = shown.sentence
        self.revealed = False
        self.note = shown.note
        # While you answer, the next word's sentence is being written.
        self.at += 1
        if self.at < len(self.questions):
            self.live.prepare(self.questions[self.at].card_id)
        return self.current

    def lines(self, sentence: Sentence) -> list[str]:
        """A sentence as shown under its word: the hanzi, and the pinyin if the mode
        shows it."""
        if "sentence_pinyin" in self.fields:
            return [sentence.hanzi, sentence.pinyin]
        return [sentence.hanzi]

    def translate(self, question: Question) -> Question | None:
        """The engine's `prepare` for the translate modes: the word's question becomes
        its sentence's, with the English as the answer. No usable sentence = skip."""
        self.skipped = None
        sentence = self.fetch(question)
        if sentence is None or not clean(sentence.english, SETTINGS):
            self.skipped = next(iter(question.shown.values()))
            return None
        shown = {"sentence": sentence.hanzi}
        if "sentence_pinyin" in self.fields:
            shown["sentence_pinyin"] = sentence.pinyin
        return Question(
            card_id=question.card_id,
            mode=question.mode,
            shown=shown,
            accepted_answers=[sentence.english],
        )

    def after_translation(self) -> list[str]:
        """After a translation: the English (unless shown), the pinyin if it was
        hidden, and the word the sentence was for."""
        if self.current is None:
            return []
        lines = [] if self.revealed else [f"= {self.current.english}"]
        if "sentence_pinyin" not in self.fields:
            lines.append(self.current.pinyin)
        card = self.cards.get(self.questions[self.at - 1].card_id)
        if card is not None:
            meaning = "; ".join(card.answers[:SHOW_ANSWERS])
            lines.append(
                f"word: {card.fields['hanzi']} ({card.fields['pinyin']}) = {meaning}"
            )
        return lines

    def finish(self) -> list[str]:
        """End of the quiz: save sentences still being written; their notes."""
        return list(self.live.finish())


class Saver:
    """Saves each final answer and moves its box (ADR 0013); counts the moves."""

    def __init__(self, store: ProgressStore, skill: str) -> None:
        self.store, self.skill = store, skill
        self.up = self.back = self.stayed = 0

    def save(self, attempt: Attempt) -> str | None:
        """Save it; a problem comes back as a warning to show (the quiz goes on, and
        the next answer tries again: a busy file may have cleared by then)."""
        try:
            old, new = save_attempt(
                self.store, attempt, self.skill, datetime.now(UTC), RULE
            )
        except ValueError as err:  # ProgressFileError, or a bad saved row
            return f"⚠️ Couldn't save this answer: {err}"
        if new is not None:  # None: couldn't check, so the box didn't move
            before = old.box if old is not None else 1  # a new word starts at box 1
            if new.box > before:
                self.up += 1
            elif new.box < before:
                self.back += 1
            else:
                self.stayed += 1
        return None

    def summary(self) -> str | None:
        if not (self.up or self.back or self.stayed):
            return None
        word = "word" if self.up == 1 else "words"
        line = f"Boxes: {self.up} {word} moved up, {self.back} back to box 1"
        return line + (f", {self.stayed} stayed." if self.stayed else ".")


def end_lines(
    result: QuizResult,
    live: bool,
    saver: Saver | None,
    live_hint: str = "try --live",
) -> list[str]:
    """The end of a quiz: skipped, stopped early, the score, the boxes moved.
    `live_hint` is how this front end says "turn live sentences on"."""
    lines = []
    if result.skipped:
        lines.append(f"Skipped {result.skipped} with no example sentence.")
    if not result.finished:
        lines.append(
            f"Stopped after {result.answered + result.skipped} of {result.total}."
        )
    if result.answered == 0 and result.skipped:
        why = "Claude couldn't write any just now" if live else live_hint
        lines.append(f"Nothing to score: no word had a sentence ({why}).")
    else:
        lines.append(f"Score: {result.correct}/{result.answered}")
    if saver is not None and (moved := saver.summary()):
        lines.append(moved)
    return lines


@dataclass
class HskQuiz:
    """Everything one quiz needs, ready to play in any front end."""

    questions: list[Question]
    mode: Mode  # the mode as chosen (its skill, where its answer comes from)
    translating: bool  # whole sentences: the answer is the sentence's English
    settings: GradeSettings
    judge: Judge | None  # Claude (word or gist rubric), or None when it's off
    sentences: SentencePart | None  # the sentence modes and translate modes
    saver: Saver | None  # None with save off

    @property
    def prepare(self) -> Callable[[Question], Question | None] | None:
        """The engine's `prepare` (translate modes: the word becomes its sentence)."""
        return self.sentences.translate if self.translating and self.sentences else None

    def session(
        self,
        judge: Judge | None = None,
        prepare: Callable[[Question], Question | None]
        | None
        | Literal[_Default.PREPARE] = _Default.PREPARE,
    ) -> QuizSession:
        """A fresh engine session; `judge` = the front end's (e.g. wrapped) judge,
        `prepare` = the front end's (e.g. wrapped to collect notes; default: ours)."""
        chosen = self.prepare if prepare is _Default.PREPARE else prepare
        return QuizSession(
            self.questions, settings=self.settings, judge=judge, prepare=chosen
        )


def build_quiz(
    options: QuizOptions,
    files: QuizFiles,
    *,
    judge_class: type[ClaudeJudge] = ClaudeJudge,
    before_asking: Callable[[], None] | None = None,
    before_writing: Callable[[], None] | None = None,
) -> HskQuiz:
    """Load the cards, deal the deck (due words first), and set up the judge, the
    sentence part and saving. Raises SetupError with the lines to show.

    `judge_class` is the judge to build (a fake in tests); `before_asking` /
    `before_writing` are called just before a slow Claude call (e.g. a spinner).
    """
    if problem := mode_problem(options.mode):
        raise SetupError(problem)
    if not files.cards.exists():
        hint = (  # the real file is made by the normalizer
            [f"Make it from {ROOT}: uv run python -m hsk_trainer.blocks.normalizer"]
            if files.cards == CARDS_FILE
            else []
        )
        raise SetupError(f"No cards file at {files.cards}.", *hint)

    wanted = HSK_MODES[options.mode]
    translating = wanted.answer_from == "sentence"
    from_bank = [f for f in wanted.show if f in SENTENCE_FIELDS]
    if translating and not from_bank:  # its answer comes from a sentence it must show
        raise SetupError(
            f"Mode {wanted.name!r} takes its answer from a sentence but shows none."
        )
    # The card has no sentence fields: they come from the bank as each word is shown.
    # A translate mode's deck is of word questions, turned into sentences one by one.
    on_card = [f for f in wanted.show if f not in from_bank] or ["hanzi"]
    shown = Mode(name=wanted.name, show=on_card, skill=wanted.skill)
    settings = TRANSLATE_SETTINGS if translating else SETTINGS
    sentences: SentencePart | None = None
    saver: Saver | None = None
    try:
        all_cards = load_cards(files.cards)
        # Only this band's cards: a bad line in another band doesn't block this quiz.
        in_band = [c for c in all_cards if c.level == options.band]
        playable = with_answers(in_band, files.answers)
        store: ProgressStore | None = None
        schedule = None
        if options.save:  # due words first, then new ones (ADR 0013)
            schedule = {}
            if files.progress.exists():  # a first quiz makes it once the quiz is ready
                store = ProgressStore(files.progress)
                schedule = {cid: b.due for cid, b in store.boxes(wanted.skill).items()}
        questions = build_deck(
            playable,
            shown,
            options.n,
            levels=[options.band],
            seed=options.seed,
            schedule=schedule,
        )
        # The bank knows every card, so other bands' lines stay as they are.
        if from_bank:
            bank = SentenceBank(
                all_cards,
                path=files.sentences,
                seen_path=files.seen,
                removed_path=files.removed,
            )
            live = LiveSentences(
                bank, all_cards, enabled=options.live, before_waiting=before_writing
            )
            by_id = {c.id: c for c in playable}
            sentences = SentencePart(live, from_bank, questions, by_id)
        # Up-front data check (a card nobody can answer), kept apart from the quiz so
        # a ValueError mid-quiz is never mislabelled as a bad file.
        QuizSession(questions, settings=SETTINGS)
        if options.save:  # only now: a quiz that can't start leaves no new file behind
            saver = Saver(store or ProgressStore(files.progress), wanted.skill)
    except ProgressFileError as err:  # your progress file (a ValueError too)
        raise SetupError(
            f"Can't use your progress file {files.progress}:",
            str(err),
            "Nothing was changed. To practise anyway: add --no-save.",
        ) from err
    except RemovedListError as err:  # the removed list (a SentenceFileError)
        raise SetupError(
            f"Can't read the removed-sentences list {files.removed}:",
            str(err),
            "Restore it with git checkout, or fix it.",
        ) from err
    except SentenceFileError as err:  # the bank (a ValueError: caught first)
        raise SetupError(
            f"Can't read the sentence bank {files.sentences}:",
            str(err),
            "Restore it with git checkout, or fix the line it names.",
        ) from err
    except (ValidationError, ValueError) as err:  # bad or partial data file
        hint = []
        if files.answers == ANSWERS_FILE and isinstance(err, AnswerFileError):
            hint = [  # the real file is committed, so this is a broken checkout
                "Restore it with git checkout, or fix it with:",
                "uv run python -m hsk_trainer.blocks.answer_writer",
            ]
        raise SetupError(
            f"Can't build a quiz from {files.cards} and {files.answers.name}:",
            str(err),
            *hint,
        ) from err
    except OSError as err:  # a data file that can't be opened
        raise SetupError(f"Can't read the quiz files: {err}") from err

    judge: Judge | None = None
    if options.judge and translating:
        judge = judge_class(
            TRANSLATE_SUBJECT,
            cache_file=files.judge_cache,
            before_asking=before_asking,
            rubric=GIST_RUBRIC,
            max_chars=GIST_MAX_CHARS,
        )
    elif options.judge:
        judge = judge_class(
            JUDGE_SUBJECT, cache_file=files.judge_cache, before_asking=before_asking
        )
    return HskQuiz(
        questions=questions,
        mode=wanted,
        translating=translating,
        settings=settings,
        judge=judge,
        sentences=sentences,
        saver=saver,
    )


# -- stats: the numbers `hsk stats` prints and the web Stats page shows ---------------


def skills() -> dict[str, list[str]]:
    """Each skill and the modes that practise it, in mode order (from config)."""
    found: dict[str, list[str]] = {}
    for m in HSK_MODES.values():
        found.setdefault(m.skill, []).append(m.name)
    return found


@dataclass
class SkillReport:
    """One skill's numbers in one band."""

    skill: str
    modes: list[str]
    stats: SkillStats


@dataclass
class BandStats:
    """One band: its size, a label per word (hanzi + pinyin), and each skill."""

    band: int
    words: int
    label: dict[str, str]
    skills: list[SkillReport]


def nothing_yet(s: SkillStats) -> bool:
    """No answer saved for this skill yet (every word new, nothing in the last week)."""
    return s.new == s.cards and not (s.recent_answered or s.recent_unchecked)


def box_counts(s: SkillStats) -> list[tuple[int, int]]:
    """(box, words in it) for every box of the rule, and any box past its last."""
    last = max([len(RULE.waits), *s.by_box])
    return [(b, s.by_box.get(b, 0)) for b in range(1, last + 1)]


def week_line(s: SkillStats) -> str:
    """The last 7 days: "41/50 right (82%)", plus answers nobody could check."""
    if s.recent_answered:
        pct = 100 * s.recent_right // s.recent_answered  # rounded down: 199/200 = 99%
        week = f"{s.recent_right}/{s.recent_answered} right ({pct}%)"
    else:
        week = "no checked answers"
    if s.recent_unchecked:
        week += f" (+{s.recent_unchecked} not checked)"
    return week


def has_progress(path: Path) -> bool:
    """Is there saved progress to show? A missing or empty file means no: the stats
    never make (or set up) the file just to look at it; the first quiz that saves does."""
    return path.exists() and not (path.is_file() and path.stat().st_size == 0)


def gather_stats(
    files: QuizFiles, band: int | None = None, now: datetime | None = None
) -> list[BandStats] | None:
    """Per band (one, or all in the cards file) and skill: the progress numbers from
    `skill_stats`. None if no progress is saved yet. Changes nothing. Raises SetupError
    (ready-to-show lines) if the cards or progress file can't be read."""
    if not has_progress(files.progress):
        return None
    try:
        all_cards = load_cards(files.cards)
    except (ValidationError, ValueError, OSError) as err:
        raise SetupError(f"Can't read the cards file {files.cards}:", str(err)) from err
    now = now or datetime.now(UTC)
    if now.utcoffset() is None:  # before the try: not the progress file's fault
        raise ValueError("now needs a timezone (e.g. datetime.now(UTC))")
    levels = sorted({c.level for c in all_cards})
    if band is not None and band not in levels:
        raise SetupError(
            f"No band {band} in the cards file {files.cards}.",
            f"Bands there: {', '.join(map(str, levels))}.",
        )
    bands = [band] if band is not None else levels
    found = skills()
    out: list[BandStats] = []
    try:
        store = ProgressStore(files.progress)
        for b in bands:
            in_band = [c for c in all_cards if c.level == b]
            # hanzi + pinyin: two readings of one character (还 hái / huán) differ
            label = {
                c.id: " ".join(
                    filter(None, [c.fields.get("hanzi", c.id), c.fields.get("pinyin")])
                )
                for c in in_band
            }
            reports = [
                SkillReport(skill, modes, skill_stats(store, label, skill, now))
                for skill, modes in found.items()
            ]
            out.append(BandStats(b, len(in_band), label, reports))
    except (ProgressFileError, OSError) as err:  # only the file's problems
        raise SetupError(
            f"Can't read your progress file {files.progress}:", str(err)
        ) from err
    return out
