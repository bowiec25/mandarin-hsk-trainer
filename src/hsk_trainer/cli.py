"""Command-line entry point: `uv run hsk quiz --band 1 --mode char --n 10`.

Not a block: it is the thin shell that wires the blocks to the keyboard and screen
(cards.jsonl -> deck_builder -> engine, graded with the cedict_cleaner).
"""

import sys
from pathlib import Path
from typing import Annotated

import typer

from hsk_trainer.blocks.cedict_cleaner import clean_answer
from hsk_trainer.modes import HSK_MODES
from quizkit.blocks.deck_builder import build_deck
from quizkit.blocks.engine import Attempt, run_quiz
from quizkit.files import load_cards
from quizkit.models import Question

# Found from this file, so `hsk` works from any folder (src/hsk_trainer/cli.py -> root).
CARDS_FILE = Path(__file__).resolve().parents[2] / "data" / "processed" / "cards.jsonl"

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


def _readable_answers(question: Question) -> list[str]:
    """The cleaned answers, as written (apostrophes kept), each once, in order."""
    answers = [kept for a in question.accepted_answers for kept in clean_answer(a)]
    return list(dict.fromkeys(answers))


def _tell(attempt: Attempt) -> None:
    g = attempt.grade
    if g.correct and g.typo:
        print(f"✅ close enough (typo): {g.matched}")
    elif g.correct:
        print("✅")
    else:
        # Not g.expected: that is the grader's normalised form ("havent"), not for people.
        answers = _readable_answers(attempt.question)
        shown = answers[:SHOW_ANSWERS]
        more = " …" if len(answers) > SHOW_ANSWERS else ""
        print(f"❌ {'; '.join(shown)}{more}")


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
    cards: Annotated[Path, typer.Option(hidden=True)] = CARDS_FILE,
) -> None:
    """Quiz yourself: see a word, type its English meaning. Ctrl-C stops (score kept)."""
    if not cards.exists():
        print(f"No cards file at {cards}.", file=sys.stderr)
        print(
            "Make it with: uv run python -m hsk_trainer.blocks.normalizer",
            file=sys.stderr,
        )
        raise typer.Exit(1)

    questions = build_deck(
        load_cards(cards), HSK_MODES[mode], n, levels=[band], seed=seed
    )
    if len(questions) < n:
        print(
            f"Only {len(questions)} band-{band} words, so the quiz has {len(questions)}."
        )
    print(
        f"Band {band}, {len(questions)} words. Type the meaning in English; Ctrl-C stops."
    )

    result = run_quiz(questions, ask=_ask, tell=_tell, cleaner=clean_answer)

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
