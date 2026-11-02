"""CI check: the PR description must fill in "## Still the right thing?".

CI passes the PR description in the PR_BODY environment variable. The check fails
(exit 1) if the section is missing, or empty once the template's <!-- hint --> is
removed. It proves the question was answered, not that the answer is good.
"""

import os
import re
import sys

HEADING = "## Still the right thing?"
MIN_CHARS = 10  # enough for "Nothing changed, ..." but not "-" or "n/a"


def is_our_heading(line: str) -> bool:
    """Any heading level; extra words after the title are fine ("... (yes)")."""
    title = line.strip().lstrip("#").strip().lower()
    return line.strip().startswith("#") and title.startswith("still the right thing")


def sections(body: str) -> list[str]:
    """The text under each "Still the right thing?" heading, up to the next heading.

    Lines inside ``` code blocks are never treated as headings.
    """
    found: list[list[str]] = []
    current: list[str] | None = None
    in_fence = False
    for line in body.replace("\r\n", "\n").split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and re.match(r"\s*#", line):  # a heading
            current = [] if is_our_heading(line) else None
            if current is not None:
                found.append(current)
            continue
        if current is not None:
            current.append(line)
    return ["\n".join(lines) for lines in found]


def answer_of(text: str) -> str:
    """The text with <!-- hints --> removed (an unclosed one hides the rest, as on GitHub)."""
    return re.sub(r"<!--.*?(-->|\Z)", "", text, flags=re.DOTALL).strip()


def check(body: str) -> str | None:
    """None if the body passes, otherwise the reason it fails."""
    found = sections(body)
    if not found:
        return (
            f'The PR description has no "{HEADING}" heading (any level, this wording).'
        )
    if not any(len(answer_of(text)) >= MIN_CHARS for text in found):
        return f'The "{HEADING}" section is empty. Say what changed from the plan.'
    return None


def main() -> int:
    problem = check(os.environ.get("PR_BODY", ""))
    if problem:
        print(f"::error::{problem}")
        return 1
    print("Still the right thing? section is filled in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
