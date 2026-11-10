"""Shared test helpers (pytest loads this file automatically)."""

from pathlib import Path

import pytest

from quizkit.files import load_cards
from quizkit.models import Card

CARDS_JSONL = Path(__file__).parent.parent / "data" / "processed" / "cards.jsonl"


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    """Safety net: no test starts the real `claude` (slow, online, uses the
    subscription). It looks "not installed"; a test that fakes it overrides this."""
    from quizkit import claude

    monkeypatch.setattr(claude.shutil, "which", lambda name: None)


@pytest.fixture(scope="session")
def real_cards() -> list[Card]:
    """All cards from the committed data/processed/cards.jsonl, loaded once per run."""
    return load_cards(CARDS_JSONL)


@pytest.fixture(autouse=True)
def no_real_progress(tmp_path, monkeypatch):
    """Safety net: no test reads or writes the learner's real data/progress.db
    (ADR 0013). Each test gets its own empty one; a test can pass --progress too.
    Only once the CLI is imported, so generic quizkit tests don't load it. A subprocess
    test is out of its reach: give it --no-save."""
    import sys

    if "hsk_trainer.cli" in sys.modules:
        monkeypatch.setattr("hsk_trainer.cli.PROGRESS_FILE", tmp_path / "progress.db")
