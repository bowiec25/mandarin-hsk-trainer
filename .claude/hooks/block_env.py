"""PreToolUse hook: block Claude from touching the secrets file `.env`.

Claude Code sends the tool call as JSON on stdin. We exit with code 2 to BLOCK
(Claude sees the message on stderr), or 0 to allow.

- File tools (Read/Edit/Write/Grep/Glob): look only at the file path or pattern,
  so writing docs that merely *mention* .env still works.
- Bash: look at the command text (rare false alarms are OK: safer to over-block).
`.env.example` is always allowed.
"""

import json
import re
import sys

# ".env" as a whole file name: not ".env.example", not "foo.env", not ".envrc".
ENV_FILE = re.compile(r"(?<![\w.-])\.env(?![\w.-])")

PATH_KEYS = {
    "Read": ["file_path"],
    "Edit": ["file_path"],
    "Write": ["file_path"],
    "Grep": ["path", "glob"],
    "Glob": ["pattern", "path"],
    "Bash": ["command"],
}


def main() -> int:
    try:
        call = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # can't read it: don't break Claude Code

    tool = call.get("tool_name", "")
    tool_input = call.get("tool_input") or {}
    for key in PATH_KEYS.get(tool, []):
        value = tool_input.get(key)
        if isinstance(value, str) and ENV_FILE.search(value):
            print(
                f"Blocked: .env holds secrets, so Claude may not access it "
                f"({tool}: {key}). Use .env.example for key names.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
