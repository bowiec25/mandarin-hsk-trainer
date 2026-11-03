"""Command-line entry point: `uv run hsk quiz --band 1 --mode char --n 10`.

Not a block: it is the thin shell that wires the blocks to the keyboard and screen
(cards.jsonl + answers.jsonl -> deck_builder -> engine's run_quiz). One answer list
decides what counts (ADR 0006): the answers in data/generated/answers.jsonl.
"""

import sys
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from hsk_trainer.blocks.answer_writer import ANSWERS_FILE, AnswerFileError, load_answers
from hsk_trainer.modes import HSK_MODES
from quizkit.blocks.deck_builder import build_deck
from quizkit.blocks.engine import Attempt, QuizSession, run_quiz
from quizkit.blocks.grader import GradeSettings, clean
from quizkit.files import load_cards
from quizkit.models import Card, Question

# Found from this file, so `hsk` works from any folder (src/hsk_trainer/cli.py -> root).
# Assumes it runs from the repo (`uv run hsk`), not from an installed wheel.
ROOT = Path(__file__).resolve().parents[2]
CARDS_FILE = ROOT / "data" / "processed" / "cards.jsonl"
SETTINGS = GradeSettings()

PLAYABLE_MODES = ("char", "char_pinyin")  # the sentence modes need M4's sentences
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
    if mode in HSK_MODES:
        raise typer.BadParameter(
            f"{mode!r} needs example sentences, which arrive in M4."
        )
    raise typer.BadParameter(
        f"{mode!r} is not a mode. Try: {', '.join(PLAYABLE_MODES)}."
    )


def _ask(question: Question) -> str | None:
    """Show the word, read the typed answer. End-of-input = quit (None).

    Ctrl-C needs nothing here: run_quiz treats it as a quit wherever it lands."""
    print()
    print("   ".join(question.shown.values()))
    try:
        return input("> ")
    except EOFError:
        print()
        return None


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
    g = attempt.grade
    readable = _readable(attempt.question)
    if g.correct and g.typo:
        print(f"✅ close enough (typo): {readable.get(g.matched, g.matched)}")
    elif g.correct:
        print("✅")
    else:
        answers = list(readable.values())
        more = " …" if len(answers) > SHOW_ANSWERS else ""
        print(f"❌ {'; '.join(answers[:SHOW_ANSWERS])}{more}")


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

    try:
        # Only this band's cards: a bad line in another band doesn't block this quiz.
        in_band = [c for c in load_cards(cards) if c.level == band]
        playable = _with_answers(in_band, answers)
        questions = build_deck(playable, HSK_MODES[mode], n, levels=[band], seed=seed)
        # Up-front data check (a card nobody can answer), kept apart from run_quiz so a
        # ValueError mid-quiz is never mislabelled as a bad file.
        QuizSession(questions, settings=SETTINGS)
    except (ValidationError, ValueError) as err:  # bad or partial data file
        hint = []
        if answers == ANSWERS_FILE and isinstance(err, AnswerFileError):
            hint = [  # the real file is committed, so this is a broken checkout
                "Restore it with git checkout, or fix it with:",
                "uv run python -m hsk_trainer.blocks.answer_writer",
            ]
        _fail(f"Can't build a quiz from {cards} and {answers.name}:", str(err), *hint)

    if len(questions) < n:
        print(
            f"Only {len(questions)} band-{band} words, so the quiz has {len(questions)}."
        )
    print(
        f"Band {band}, {len(questions)} words. Type the meaning in English; Ctrl-C stops."
    )

    # run_quiz treats Ctrl-C anywhere in its loop as a quit, so the score is kept.
    result = run_quiz(questions, ask=_ask, tell=_tell, settings=SETTINGS)

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
