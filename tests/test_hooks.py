"""Tests for the Claude Code hook scripts in .claude/hooks/.

Each hook gets a tool call as JSON on stdin (the same way Claude Code calls it),
and we check what it does: exit code 2 = blocked, 0 = allowed.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / ".claude" / "hooks"


def run_hook(
    script: str, tool_name: str, tool_input: dict
) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=payload,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )


# ---- block_env.py: the .env lock ----------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Read", {"file_path": "C:\\Users\\me\\proj\\.env"}),
        ("Read", {"file_path": "/home/me/proj/.env"}),
        ("Edit", {"file_path": ".env", "old_string": "a", "new_string": "b"}),
        ("Write", {"file_path": "./.env", "content": "KEY=1"}),
        ("Grep", {"pattern": "KEY", "path": ".env"}),
        ("Glob", {"pattern": "**/.env"}),
        ("Bash", {"command": "cat .env"}),
        ("Bash", {"command": "type C:\\proj\\.env"}),
        ("Bash", {"command": "source ./.env && echo hi"}),
    ],
)
def test_env_access_is_blocked(tool, tool_input):
    result = run_hook("block_env.py", tool, tool_input)
    assert result.returncode == 2
    assert "Blocked" in result.stderr


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Read", {"file_path": ".env.example"}),
        ("Read", {"file_path": "README.md"}),
        # Writing docs that merely *mention* .env must still work:
        ("Write", {"file_path": "docs/SETUP_LOG.md", "content": "Never commit .env"}),
        (
            "Edit",
            {"file_path": "CLAUDE.md", "old_string": "x", "new_string": "see .env"},
        ),
        ("Bash", {"command": "cp .env.example example-copy.txt"}),
        ("Bash", {"command": "uv run pytest"}),
        ("Glob", {"pattern": "**/*.py"}),
    ],
)
def test_safe_actions_are_allowed(tool, tool_input):
    result = run_hook("block_env.py", tool, tool_input)
    assert result.returncode == 0, result.stderr


def test_bad_input_does_not_crash_or_block():
    result = subprocess.run(
        [sys.executable, str(HOOKS / "block_env.py")],
        input="not json",
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0


# ---- format_python.py: auto-tidy ------------------------------------------------------


def test_python_file_gets_formatted(tmp_path):
    messy = tmp_path / "messy.py"
    messy.write_text("x=[1,2,\n3]\ndef f( a ):\n  return a\n", encoding="utf-8")
    result = run_hook("format_python.py", "Edit", {"file_path": str(messy)})
    assert result.returncode == 0
    assert (
        messy.read_text(encoding="utf-8")
        == "x = [1, 2, 3]\n\n\ndef f(a):\n    return a\n"
    )


def test_non_python_file_is_left_alone(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("x=[1,2]\n", encoding="utf-8")
    result = run_hook("format_python.py", "Write", {"file_path": str(note)})
    assert result.returncode == 0
    assert note.read_text(encoding="utf-8") == "x=[1,2]\n"
