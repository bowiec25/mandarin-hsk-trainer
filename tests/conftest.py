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
    """Safety net: no test reads or writes the learner's own files: progress
    (data/progress.db, ADR 0013), the judge cache, or when each sentence was last shown
    (data/sentence_seen.json). Each test gets its own empty ones (a test can still
    give its own paths). Inherited by a subprocess test, unless it clears the
    environment: then give it --no-save and its own files."""
    # Set in the environment: read whenever a quiz is set up, by any module imported
    # at any time, and inherited by a test that runs the program in a subprocess.
    monkeypatch.setenv("HSK_PROGRESS_FILE", str(tmp_path / "progress.db"))
    monkeypatch.setenv("HSK_JUDGE_CACHE", str(tmp_path / "judge_cache.jsonl"))
    monkeypatch.setenv("HSK_SEEN_FILE", str(tmp_path / "sentence_seen.json"))
