"""Command-line entry point: `uv run hsk quiz --band 1 --mode char --n 10`.

Not a block: it is the thin shell that wires the blocks to the keyboard and screen
(cards.jsonl -> deck_builder -> engine's QuizSession, graded with the cedict_cleaner).
"""

import sys
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from hsk_trainer.blocks.cedict_cleaner import clean_answer
from hsk_trainer.modes import HSK_MODES
from quizkit.blocks.deck_builder import build_deck
from quizkit.blocks.engine import Attempt, QuizSession
from quizkit.blocks.grader import GradeSettings, clean
from quizkit.files import load_cards
from quizkit.models import Question

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
    """Show the word, read the typed answer. Ctrl-C or end-of-input = quit (None)."""
    print()
    print("   ".join(question.shown.values()))
    try:
        return input("> ")
    except (KeyboardInterrupt, EOFError):
        print()
        return None


def _readable(question: Question) -> dict[str, str]:
    """Each answer the grader accepts, in its normalised form -> as written for people.

    The grader compares normalised text ("haven't" -> "havent", "to love" -> "love");
    showing that would teach misspellings. Same order and de-duplication as the grader.
    """
    readable: dict[str, str] = {}
    for raw in question.accepted_answers:
        for variant in clean_answer(raw):
            key = clean(variant, SETTINGS)
            if key and key not in readable:
                readable[key] = variant
    return readable


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

    try:
        questions = build_deck(
            load_cards(cards), HSK_MODES[mode], n, levels=[band], seed=seed
        )
        session = QuizSession(questions, cleaner=clean_answer, settings=SETTINGS)
    except (ValidationError, ValueError) as err:  # bad or partial data file
        _fail(f"Can't build a quiz from {cards}:", str(err))

    if len(questions) < n:
        print(
            f"Only {len(questions)} band-{band} words, so the quiz has {len(questions)}."
        )
    print(
        f"Band {band}, {len(questions)} words. Type the meaning in English; Ctrl-C stops."
    )

    # Our own loop over QuizSession (not run_quiz), so a Ctrl-C landing *anywhere* in
    # it still keeps the score: on Windows it can arrive just after input() returns.
    try:
        while (question := session.current) is not None:
            typed = _ask(question)
            if typed is None:
                break
            _tell(session.answer(typed))
    except KeyboardInterrupt:
        print()

    result = session.result()
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
