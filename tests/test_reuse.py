"""The M3 reuse check: quizkit works for a quiz that has nothing to do with Mandarin.

Two guards:
- a scan: no file in src/quizkit imports hsk_trainer (ADR 0003: generic stays generic);
- a run: the toy capitals quiz plays to the end in a fresh Python where importing
  hsk_trainer is blocked, so any hidden dependency would crash it.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
QUIZKIT = ROOT / "src" / "quizkit"
CAPITALS = ROOT / "examples" / "capitals_quiz.py"

# Files that may *name* hsk_trainer as text (never import it), each with its reason.
ALLOWED_MENTIONS = {
    # the /new-block tool: "hsk_trainer" is one of the two package folders it writes to
    QUIZKIT / "scaffold.py",
}


def imported_modules(file: Path) -> set[str]:
    tree = ast.parse(file.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_quizkit_never_imports_hsk_trainer():
    files = sorted(QUIZKIT.rglob("*.py"))
    assert len(files) > 5  # the scan really found the package
    offenders = [
        f"{f.relative_to(ROOT).as_posix()}: {m}"
        for f in files
        for m in imported_modules(f)
        if m == "hsk_trainer" or m.startswith("hsk_trainer.")
    ]
    assert not offenders, offenders


def test_quizkit_never_mentions_hsk_trainer():
    """Catches what the import scan can't, e.g. importlib.import_module("hsk_trainer").
    Strict on purpose: even a comment naming it fails, so generic code stays generic."""
    mentions = [
        f.relative_to(ROOT).as_posix()
        for f in sorted(QUIZKIT.rglob("*.py"))
        if f not in ALLOWED_MENTIONS and "hsk_trainer" in f.read_text(encoding="utf-8")
    ]
    assert not mentions, mentions


def test_scan_would_catch_an_hsk_import(tmp_path):
    """The scan itself works: a planted import is found."""
    planted = tmp_path / "bad.py"
    planted.write_text("from hsk_trainer.modes import HSK_MODES\n", encoding="utf-8")
    assert "hsk_trainer.modes" in imported_modules(planted)


# Runs in a fresh Python: block hsk_trainer, load the example, and swap its `ask` for
# one that answers every question right (by card id, from the example's own cards).
# No PYTHONIOENCODING: the example must make its own output UTF-8-safe.
PLAY = f"""
import runpy, sys
sys.modules["hsk_trainer"] = None  # any `import hsk_trainer...` now raises ImportError
quiz = runpy.run_path({str(CAPITALS)!r})
capital = {{c.id: c.answers[0] for c in quiz["CARDS"]}}
quiz["main"].__globals__["ask"] = lambda question: capital[question.card_id]
quiz["main"]()
print("N =", quiz["N"])
"""


def test_capitals_quiz_runs_with_hsk_trainer_blocked():
    proc = subprocess.run(
        [sys.executable, "-c", PLAY],
        stdin=subprocess.DEVNULL,  # if the ask swap ever stops working: quit, not hang
        capture_output=True,
        check=False,
        timeout=60,
        env={
            k: v
            for k, v in os.environ.items()
            if k not in ("PYTHONIOENCODING", "PYTHONUTF8")
        },
    )
    err = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, err
    out = proc.stdout.decode("utf-8")
    n = int(out.rsplit("N =", 1)[1])
    assert out.count("✅") == n
    assert f"Score: {n}/{n}" in out


def test_the_block_really_blocks():
    """Sanity: in that setup, importing hsk_trainer does fail."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            'import sys; sys.modules["hsk_trainer"] = None; import hsk_trainer.cli',
        ],
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode != 0
    assert b"ImportError" in proc.stderr or b"ModuleNotFoundError" in proc.stderr
