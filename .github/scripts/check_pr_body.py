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


def section_text(body: str) -> str | None:
    """The text under the heading (up to the next ## heading), or None if absent."""
    lines = body.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        if line.strip().lower() == HEADING.lower():
            rest = []
            for later in lines[i + 1 :]:
                if later.startswith("## "):
                    break
                rest.append(later)
            return "\n".join(rest)
    return None


def check(body: str) -> str | None:
    """None if the body passes, otherwise the reason it fails."""
    text = section_text(body)
    if text is None:
        return f'The PR description has no "{HEADING}" section.'
    answer = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()
    if len(answer) < MIN_CHARS:
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
