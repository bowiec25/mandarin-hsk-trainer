"""Retired designs stay retired: their names must not come back in code, tests or SPECs.

ADR 0006 retired the rule-based `cedict_cleaner` and the grader's `cleaner` slot (one
answer list instead). Docs may still name them as history (ADRs, SETUP_LOG, snapshots).
This file is the one place that names them, to check they're gone.
"""

import inspect
import re
from pathlib import Path

import pytest

from quizkit.blocks import engine, grader

ROOT = Path(__file__).parent.parent
THIS_FILE = Path(__file__).resolve()
# The retired block and function, as whole names ("all_clean_answers" is not
# "clean_answer"). The plain word "cleaner" is fine; test_cleaner_slot_is_gone checks
# the slot itself.
RETIRED = {
    name: re.compile(rf"\b{re.escape(name)}\b")
    for name in ("cedict_cleaner", "clean_answer")
}


def scanned_files() -> list[Path]:
    """Code, tests, and each block's SPEC.md (SPECs describe the code as it is now)."""
    return sorted(
        p
        for folder in ("src", "tests", "examples")
        for pattern in ("*.py", "SPEC.md")
        for p in (ROOT / folder).rglob(pattern)
        if p.resolve() != THIS_FILE
    )


def test_retired_names_are_gone():
    files = scanned_files()
    assert len(files) > 20  # the scan really found the code
    hits = [
        f"{f.relative_to(ROOT).as_posix()}: {name}"
        for f in files
        for name, pattern in RETIRED.items()
        if pattern.search(f.read_text(encoding="utf-8"))
    ]
    assert not hits, hits


def test_whole_name_match_ignores_longer_names():
    assert RETIRED["clean_answer"].search("def test_all_clean_answers():") is None
    assert RETIRED["clean_answer"].search("from x import clean_answer") is not None


def test_cedict_cleaner_folder_is_gone():
    assert not (ROOT / "src" / "hsk_trainer" / "blocks" / "cedict_cleaner").exists()


@pytest.mark.parametrize(
    ("block", "functions"),
    [(grader, [grader.grade]), (engine, [engine.QuizSession, engine.run_quiz])],
)
def test_cleaner_slot_is_gone(block, functions):
    assert "cleaner" not in block.BLOCK_SPEC.inputs
    for function in functions:
        assert "cleaner" not in inspect.signature(function).parameters, function
