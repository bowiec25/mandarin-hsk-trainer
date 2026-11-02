"""Tests for .github/scripts/check_pr_body.py (the "Still the right thing?" CI check)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github" / "scripts" / "check_pr_body.py"
TEMPLATE = ROOT / ".github" / "pull_request_template.md"


def run_check(body: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PR_BODY"}
    if body is not None:
        env["PR_BODY"] = body
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        env=env,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )


GOOD = "## What\nx\n\n## Still the right thing?\nNothing changed, the plan holds.\n\n## How tested\npytest\n"


def test_filled_section_passes():
    assert run_check(GOOD).returncode == 0


def test_windows_line_endings_pass():
    assert run_check(GOOD.replace("\n", "\r\n")).returncode == 0


def test_heading_case_insensitive():
    assert run_check(GOOD.replace("Still the right", "still The Right")).returncode == 0


@pytest.mark.parametrize(
    "body",
    [
        "",
        "## What\nx\n## How tested\ny\n",  # section missing
        "## Still the right thing?\n\n## How tested\ny\n",  # empty
        "## Still the right thing?\n<!-- hint text that is long enough -->\n## How tested\n",
        "## Still the right thing?\nn/a\n## How tested\ny\n",  # too short
        "## What\nStill the right thing? yes, a lot of words here\n",  # not a heading
    ],
)
def test_missing_or_empty_section_fails(body):
    result = run_check(body)
    assert result.returncode == 1
    assert "::error::" in result.stdout


def test_no_pr_body_env_fails():
    assert run_check(None).returncode == 1


def test_answer_after_hint_counts():
    body = "## Still the right thing?\n<!-- hint -->\nAnswer goes on this line.\n"
    assert run_check(body).returncode == 0


def test_text_under_next_heading_does_not_count():
    body = "## Still the right thing?\n\n## How tested\nlots of testing words here\n"
    assert run_check(body).returncode == 1


@pytest.mark.parametrize(
    "heading", ["### Still the right thing?", "## Still the right thing? (yes)"]
)
def test_heading_variants_pass(heading):
    body = f"{heading}\nNothing changed, the plan holds.\n"
    assert run_check(body).returncode == 0


@pytest.mark.parametrize("next_heading", ["# Notes", "##Notes", "  ## Notes"])
def test_any_later_heading_ends_the_section(next_heading):
    body = f"## Still the right thing?\n\n{next_heading}\nlots of note words here\n"
    assert run_check(body).returncode == 1


def test_heading_inside_code_block_does_not_end_section():
    body = "## Still the right thing?\nYes:\n```\n## Example\n```\n## How tested\n"
    assert run_check(body).returncode == 0


def test_unclosed_hint_does_not_count():
    body = (
        "## Still the right thing?\n<!-- Required (CI fails if empty)\n## How tested\n"
    )
    assert run_check(body).returncode == 1


def test_any_filled_copy_of_the_section_passes():
    body = "## Still the right thing?\n<!-- hint -->\n## Still the right thing?\nNothing changed, the plan holds.\n"
    assert run_check(body).returncode == 0


def test_unfilled_pr_template_fails():
    """The template as-is (only the hint) must fail, so it has to be filled in."""
    assert run_check(TEMPLATE.read_text(encoding="utf-8")).returncode == 1


def test_template_has_the_section():
    assert "## Still the right thing?" in TEMPLATE.read_text(encoding="utf-8")
