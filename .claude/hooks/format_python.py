"""PostToolUse hook: after Claude edits a Python file, tidy it with `ruff format`.

Claude Code sends the tool call as JSON on stdin. This hook never blocks:
it always exits 0, even if formatting fails (CI will still catch problems).
"""

import json
import subprocess
import sys


def main() -> int:
    try:
        call = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    path = (call.get("tool_input") or {}).get("file_path", "")
    if isinstance(path, str) and path.endswith(".py"):
        subprocess.run(
            ["uv", "run", "--quiet", "ruff", "format", "--quiet", path],
            check=False,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
