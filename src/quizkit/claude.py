"""Ask Claude one question through headless Claude Code (`claude -p`), ADR 0005.

Generic: any quiz's agents can use it. It runs under the user's Claude subscription
(no API key). Claude gets **no tools** (`--tools ""`), so it can only answer, and it
runs in an empty temporary folder, so no project files or CLAUDE.md are loaded.
"""

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

DEFAULT_TIMEOUT = 300  # seconds; a 40-card chunk can take a while


class ClaudeError(RuntimeError):
    """Claude couldn't be used: not installed, not logged in, timeout, or an error."""


class ClaudeReply(BaseModel):
    """Claude's answer text, plus what it used (for the agent's log)."""

    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    input_tokens: int  # incl. cached prompt tokens
    output_tokens: int
    cost_usd: float  # list-price equivalent; not a charge on a subscription


Runner = Callable[..., subprocess.CompletedProcess]


def build_command(exe: str, model: str, system: str) -> list[str]:
    return [
        exe,
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--tools",
        "",  # no tools at all
        "--no-session-persistence",
        "--strict-mcp-config",  # no MCP servers
        "--system-prompt",
        system,
    ]


def parse_reply(stdout: str, model: str) -> ClaudeReply:
    """Turn `claude -p --output-format json` output into a ClaudeReply."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as err:
        raise ClaudeError(f"claude did not return JSON: {stdout[:200]!r}") from err
    if not isinstance(data, dict):
        raise ClaudeError(f"unexpected reply from claude: {stdout[:200]!r}")
    if data.get("is_error") or data.get("subtype", "success") != "success":
        raise ClaudeError(f"claude reported an error: {data.get('result', data)!r}")
    try:
        return _reply_from(data, model)
    except (TypeError, ValueError, AttributeError) as err:
        raise ClaudeError(f"unexpected usage data from claude: {err}") from err


def _reply_from(data: dict, model: str) -> ClaudeReply:
    usage = data.get("usage") or {}
    by_model = data.get("modelUsage") or {}
    # Claude Code may use a small helper model too: log the one that wrote the most.
    models = sorted(
        by_model,
        key=lambda m: -int((by_model[m] or {}).get("outputTokens", 0)),
    )
    return ClaudeReply(
        text=str(data.get("result", "")),
        model=models[0] if models else model,
        input_tokens=int(usage.get("input_tokens", 0))
        + int(usage.get("cache_creation_input_tokens", 0))
        + int(usage.get("cache_read_input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        cost_usd=float(data.get("total_cost_usd", 0.0)),
    )


def ask_claude(
    prompt: str,
    model: str = "sonnet",
    system: str = "You are a careful assistant. Follow the instructions exactly.",
    timeout: float = DEFAULT_TIMEOUT,
    run: Runner = subprocess.run,
) -> ClaudeReply:
    """Send `prompt` to Claude and return its reply. Raises ClaudeError on failure.

    `run` is swappable so tests never start the real `claude`.
    """
    exe = shutil.which("claude")
    if exe is None:
        raise ClaudeError(
            "The `claude` command was not found. Install Claude Code, run `claude` "
            "once and log in, then try again."
        )
    with tempfile.TemporaryDirectory() as empty_dir:
        try:
            result = run(
                build_command(exe, model, system),
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=empty_dir,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as err:
            raise ClaudeError(f"claude took longer than {timeout:g} s") from err
        except OSError as err:
            raise ClaudeError(f"could not start claude: {err}") from err
    if result.returncode != 0:
        if result.stdout.strip():
            parse_reply(result.stdout, model)  # raises with Claude's own message
        hint = (result.stderr or "").strip()[:300]
        raise ClaudeError(
            f"claude exited with code {result.returncode}: {hint or 'no message'} "
            "(if you're not logged in, run `claude` and log in)"
        )
    return parse_reply(result.stdout, model)
