"""Command-line entry point: `uv run hsk quiz --band 1 --mode char --n 10`.

Not a block: it is the thin shell that wires the blocks to the keyboard and screen
(cards.jsonl + answers.jsonl -> deck_builder -> engine's run_quiz). One answer list
decides what counts (ADR 0006): the answers in data/generated/answers.jsonl. An answer
the list misses goes to the Claude judge (ADR 0007), unless --no-judge. The sentence
modes show an example sentence from the bank (ADR 0011, `sentence_bank`).
"""

import sys
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from hsk_trainer.blocks.answer_writer import ANSWERS_FILE, AnswerFileError, load_answers
from hsk_trainer.blocks.sentence_bank import SEEN_FILE, SentenceBank
from hsk_trainer.blocks.sentence_writer import (
    SENTENCES_FILE,
    Sentence,
    SentenceFileError,
)
from hsk_trainer.modes import HSK_MODES
from quizkit.blocks.deck_builder import build_deck
from quizkit.blocks.engine import Attempt, QuizSession, run_quiz
from quizkit.blocks.grader import GradeSettings, clean
from quizkit.blocks.judge import ClaudeJudge
from quizkit.files import load_cards
from quizkit.models import Card, Question
from quizkit.modes import Mode

# Found from this file, so `hsk` works from any folder (src/hsk_trainer/cli.py -> root).
# Assumes it runs from the repo (`uv run hsk`), not from an installed wheel.
ROOT = Path(__file__).resolve().parents[2]
CARDS_FILE = ROOT / "data" / "processed" / "cards.jsonl"
JUDGE_CACHE = ROOT / "data" / "judge_cache.jsonl"  # gitignored: verdicts, not source
SETTINGS = GradeSettings()
# The only HSK part of the judge: what the quiz is about (ADR 0007).
JUDGE_SUBJECT = (
    "Chinese vocabulary for learners of HSK 3.0, bands 1-3. The learner sees a "
    "Chinese word and types its English meaning."
)

PLAYABLE_MODES = tuple(HSK_MODES)
SENTENCE_FIELDS = ("sentence", "sentence_pinyin")  # from the bank, not the card
SHOW_ANSWERS = 4  # how many accepted answers to show after a wrong one

app = typer.Typer(
    help="HSK 3.0 vocab trainer (bands 1-3).",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)


@app.callback()
def _root() -> None:
    """HSK 3.0 vocab trainer (bands 1-3)."""  # keeps `quiz` a named subcommand


def _check_mode(mode: str) -> str:
    if mode in PLAYABLE_MODES:
        return mode
    raise typer.BadParameter(
        f"{mode!r} is not a mode. Try: {', '.join(PLAYABLE_MODES)}."
    )


class _Sentences:
    """The sentence part of a question: shown under the word, its English after the
    answer (ADR 0011). Only used by the sentence modes."""

    def __init__(self, bank: SentenceBank, fields: list[str]) -> None:
        self.bank = bank
        self.fields = fields  # which of SENTENCE_FIELDS the mode shows, in order
        self.current: Sentence | None = None
        self.warned = False  # the seen file couldn't be saved (said once)

    def show(self, question: Question) -> None:
        self.current = self.bank.banked(question.card_id)
        if self.current is None:
            print("   (no example sentence yet for this word)")
            return
        try:
            self.bank.mark_seen(question.card_id, self.current)
        except OSError as err:  # e.g. OneDrive or antivirus has it locked: carry on
            if not self.warned:
                print(f"   (couldn't save which sentences you've seen: {err})")
                self.warned = True
        print(f"   {self.current.hanzi}")
        if "sentence_pinyin" in self.fields:
            print(f"   {self.current.pinyin}")

    def after(self) -> None:
        if self.current is not None:
            print(f"   = {self.current.english}")


def _show(question: Question) -> None:
    print()
    print("   ".join(question.shown.values()))


def _read() -> str | None:
    """The typed answer; end-of-input = quit (None)."""
    try:
        return input("> ")
    except EOFError:
        print()
        return None


def _ask(question: Question) -> str | None:
    """Show the word, read the typed answer. End-of-input = quit (None).

    Ctrl-C needs nothing here: run_quiz treats it as a quit wherever it lands."""
    _show(question)
    return _read()


def _readable(question: Question) -> dict[str, str]:
    """Each accepted answer, in the grader's normalised form -> as written for people.

    The grader compares normalised text ("haven't" -> "havent", "to love" -> "love");
    showing that would teach misspellings. Same order and de-duplication as the grader.
    """
    readable: dict[str, str] = {}
    for answer in question.accepted_answers:
        key = clean(answer, SETTINGS)
        if key and key not in readable:
            readable[key] = answer
    return readable


def _with_answers(cards: list[Card], answers_file: Path) -> list[Card]:
    """Each card with its answers from answers.jsonl (the one answer list, ADR 0006).

    load_answers checks the file with the writer's own checker; Card re-checks each
    card. Raises ValueError (AnswerFileError is one) for a bad or incomplete file.
    """
    answers = load_answers(answers_file, cards)
    return [
        Card.model_validate({**c.model_dump(), "answers": answers[c.id]}) for c in cards
    ]


def _tell(attempt: Attempt) -> None:
    g, verdict = attempt.grade, attempt.verdict
    readable = _readable(attempt.question)
    if g.correct and g.typo:
        print(f"✅ close enough (typo): {readable.get(g.matched, g.matched)}")
    elif g.correct:
        print("✅")
    elif verdict is not None and verdict.correct:
        print(f"✅ accepted by the Claude judge: {verdict.reason}")
    else:
        answers = list(readable.values())
        more = " …" if len(answers) > SHOW_ANSWERS else ""
        print(f"❌ {'; '.join(answers[:SHOW_ANSWERS])}{more}")
        if verdict is not None and verdict.source == "not_checked":
            print(f"   (judge {verdict.reason})")
        elif verdict is not None:
            print(f"   judge: {verdict.reason}")


def _asking() -> None:
    print("   asking the judge…", flush=True)


def _fail(*lines: str) -> NoReturn:
    for line in lines:
        print(line, file=sys.stderr)
    raise typer.Exit(1)


@app.command()
def quiz(
    band: Annotated[
        int, typer.Option(min=1, max=3, help="HSK band: only its new words.")
    ] = 1,
    mode: Annotated[
        str,
        typer.Option(
            callback=_check_mode, help=f"What to show: {', '.join(PLAYABLE_MODES)}."
        ),
    ] = "char",
    n: Annotated[int, typer.Option("--n", min=1, help="How many words.")] = 10,
    seed: Annotated[
        int | None, typer.Option(help="Same seed, same words (for replays).")
    ] = None,
    cards: Annotated[Path | None, typer.Option(hidden=True)] = None,
    answers: Annotated[Path | None, typer.Option(hidden=True)] = None,
    sentences: Annotated[Path | None, typer.Option(hidden=True)] = None,
    seen: Annotated[Path | None, typer.Option(hidden=True)] = None,
    judge: Annotated[
        bool,
        typer.Option(
            "--judge/--no-judge",
            help="Ask Claude about answers the list misses (needs `claude`, online).",
        ),
    ] = True,
) -> None:
    """Quiz yourself: see a word, type its English meaning. Ctrl-C stops (score kept)."""
    if cards is None:  # looked up now, not at import, so tests can point it elsewhere
        cards = CARDS_FILE
        if not cards.exists():
            _fail(
                f"No cards file at {cards}.",
                f"Make it from {ROOT}: uv run python -m hsk_trainer.blocks.normalizer",
            )
    elif not cards.exists():
        _fail(f"No cards file at {cards}.")
    answers = answers or ANSWERS_FILE

    wanted = HSK_MODES[mode]
    from_bank = [f for f in wanted.show if f in SENTENCE_FIELDS]
    # The card has no sentence fields: they come from the bank as each word is shown.
    shown = Mode(name=wanted.name, show=[f for f in wanted.show if f not in from_bank])
    sentence_part: _Sentences | None = None
    try:
        all_cards = load_cards(cards)
        # Only this band's cards: a bad line in another band doesn't block this quiz.
        in_band = [c for c in all_cards if c.level == band]
        playable = _with_answers(in_band, answers)
        questions = build_deck(playable, shown, n, levels=[band], seed=seed)
        # The bank knows every card, so other bands' lines stay as they are.
        if from_bank:
            bank = SentenceBank(
                all_cards, path=sentences or SENTENCES_FILE, seen_path=seen or SEEN_FILE
            )
            sentence_part = _Sentences(bank, from_bank)
        # Up-front data check (a card nobody can answer), kept apart from run_quiz so a
        # ValueError mid-quiz is never mislabelled as a bad file.
        QuizSession(questions, settings=SETTINGS)
    except SentenceFileError as err:  # the bank (a ValueError: caught first)
        _fail(
            f"Can't read the sentence bank {sentences or SENTENCES_FILE}:",
            str(err),
            "Restore it with git checkout, or fix the line it names.",
        )
    except (ValidationError, ValueError) as err:  # bad or partial data file
        hint = []
        if answers == ANSWERS_FILE and isinstance(err, AnswerFileError):
            hint = [  # the real file is committed, so this is a broken checkout
                "Restore it with git checkout, or fix it with:",
                "uv run python -m hsk_trainer.blocks.answer_writer",
            ]
        _fail(f"Can't build a quiz from {cards} and {answers.name}:", str(err), *hint)
    except OSError as err:  # a data file that can't be opened
        _fail(f"Can't read the quiz files: {err}")

    if len(questions) < n:
        print(
            f"Only {len(questions)} band-{band} words, so the quiz has {len(questions)}."
        )
    print(
        f"Band {band}, {len(questions)} words. Type the meaning in English; Ctrl-C stops."
    )

    # run_quiz treats Ctrl-C anywhere in its loop as a quit, so the score is kept.
    judge_fn = (
        ClaudeJudge(JUDGE_SUBJECT, cache_file=JUDGE_CACHE, before_asking=_asking)
        if judge
        else None
    )
    ask, tell = _ask, _tell
    if sentence_part is not None:  # the sentence modes: a sentence under each word
        part = sentence_part

        def ask(question: Question) -> str | None:
            _show(question)
            part.show(question)
            return _read()

        def tell(attempt: Attempt) -> None:
            _tell(attempt)
            part.after()

    result = run_quiz(questions, ask=ask, tell=tell, settings=SETTINGS, judge=judge_fn)

    print()
    if not result.finished:
        print(f"Stopped after {result.answered} of {result.total}.")
    print(f"Score: {result.correct}/{result.answered}")


def _utf8_output() -> None:
    """Windows pipes default to an old code page that can't print 爱 or ài."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main() -> None:
    _utf8_output()
    app()
