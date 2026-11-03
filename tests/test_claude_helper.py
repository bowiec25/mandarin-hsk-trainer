"""Tests for quizkit.claude (the `claude -p` helper). The real `claude` never runs."""

import json
import subprocess

import pytest

from quizkit import claude
from quizkit.claude import ClaudeError, ask_claude, parse_reply

GOOD = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": '{"ok": true}',
    "total_cost_usd": 0.0026,
    "usage": {
        "input_tokens": 2,
        "cache_creation_input_tokens": 100,
        "cache_read_input_tokens": 50,
        "output_tokens": 9,
    },
    "modelUsage": {"claude-sonnet-5-5": {}},
}


@pytest.fixture(autouse=True)
def fake_claude_installed(monkeypatch):
    monkeypatch.setattr(claude.shutil, "which", lambda name: "/bin/claude")


def fake_run(stdout="", returncode=0, stderr="", raises=None, seen=None):
    def run(cmd, **kwargs):
        if seen is not None:
            seen.append((cmd, kwargs))
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

    return run


def test_good_reply_is_parsed():
    reply = ask_claude("hi", run=fake_run(json.dumps(GOOD)))
    assert reply.text == '{"ok": true}'
    assert reply.model == "claude-sonnet-5-5"
    assert reply.input_tokens == 152  # cached tokens count too
    assert reply.output_tokens == 9
    assert reply.cost_usd == pytest.approx(0.0026)


def test_command_has_no_tools_and_prompt_on_stdin():
    seen = []
    ask_claude("the prompt", model="haiku", run=fake_run(json.dumps(GOOD), seen=seen))
    cmd, kwargs = seen[0]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "haiku"
    assert "-p" in cmd and "--strict-mcp-config" in cmd
    assert kwargs["input"] == "the prompt"
    assert kwargs["cwd"]  # an empty temp folder, not the project


def test_not_installed(monkeypatch):
    monkeypatch.setattr(claude.shutil, "which", lambda name: None)
    with pytest.raises(ClaudeError, match="not found"):
        ask_claude("hi", run=fake_run(json.dumps(GOOD)))


def test_timeout():
    err = subprocess.TimeoutExpired("claude", 5)
    with pytest.raises(ClaudeError, match="longer than"):
        ask_claude("hi", timeout=5, run=fake_run(raises=err))


def test_cannot_start():
    with pytest.raises(ClaudeError, match="could not start"):
        ask_claude("hi", run=fake_run(raises=OSError("boom")))


def test_nonzero_exit_without_output():
    with pytest.raises(ClaudeError, match="code 1.*log in"):
        ask_claude("hi", run=fake_run("", returncode=1, stderr="Not logged in"))


@pytest.mark.parametrize(
    "stdout",
    [
        "not json",
        "[1, 2]",
        json.dumps({**GOOD, "is_error": True, "result": "usage limit reached"}),
        json.dumps({**GOOD, "subtype": "error_max_turns"}),
    ],
)
def test_bad_or_error_replies(stdout):
    with pytest.raises(ClaudeError):
        parse_reply(stdout, "sonnet")


def test_missing_usage_defaults_to_zero():
    reply = parse_reply(json.dumps({"result": "x"}), "sonnet")
    assert (reply.text, reply.model, reply.input_tokens, reply.cost_usd) == (
        "x",
        "sonnet",
        0,
        0.0,
    )


def test_nonzero_exit_with_json_error_is_reported():
    body = json.dumps({**GOOD, "is_error": True, "result": "usage limit reached"})
    with pytest.raises(ClaudeError, match="usage limit"):
        ask_claude("hi", run=fake_run(body, returncode=1))


def test_model_that_wrote_most_is_logged():
    body = {
        **GOOD,
        "modelUsage": {"small": {"outputTokens": 3}, "big": {"outputTokens": 90}},
    }
    assert parse_reply(json.dumps(body), "sonnet").model == "big"


@pytest.mark.parametrize(
    "extra", [{"usage": {"output_tokens": "lots"}}, {"modelUsage": {"m": "x"}}]
)
def test_odd_usage_data_is_a_claude_error(extra):
    with pytest.raises(ClaudeError, match="usage"):
        parse_reply(json.dumps({**GOOD, **extra}), "sonnet")


def test_nonzero_exit_with_success_json_is_still_an_error():
    with pytest.raises(ClaudeError, match="code 1"):
        ask_claude("hi", run=fake_run(json.dumps(GOOD), returncode=1))


def test_nonzero_exit_with_non_json_keeps_the_login_hint():
    with pytest.raises(ClaudeError, match="log in"):
        ask_claude("hi", run=fake_run("Error: not logged in", returncode=1))


# -- json_schema option (judge SPEC, Tools) -----------------------------------------

SCHEMA = {
    "type": "object",
    "properties": {"reason": {"type": "string"}, "correct": {"type": "boolean"}},
    "required": ["reason", "correct"],
}
STRUCTURED = {
    **GOOD,
    "result": "Here is my verdict.",
    "structured_output": {"correct": True, "reason": "Papa means dad."},
}


def test_json_schema_is_passed_on_the_command_line():
    seen = []
    ask_claude(
        "hi", json_schema=SCHEMA, run=fake_run(json.dumps(STRUCTURED), seen=seen)
    )
    cmd, _ = seen[0]
    assert "--json-schema" in cmd
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == SCHEMA


def test_json_schema_reply_text_comes_from_structured_output():
    reply = ask_claude("hi", json_schema=SCHEMA, run=fake_run(json.dumps(STRUCTURED)))
    assert json.loads(reply.text) == {"correct": True, "reason": "Papa means dad."}
    assert reply.model == "claude-sonnet-5-5"  # usage is still read as before
    assert reply.input_tokens == 152
    assert reply.output_tokens == 9


def test_no_json_schema_is_unchanged():
    seen = []
    reply = ask_claude("hi", run=fake_run(json.dumps(STRUCTURED), seen=seen))
    cmd, _ = seen[0]
    assert "--json-schema" not in cmd
    assert reply.text == "Here is my verdict."  # `result`, not structured_output


def test_json_schema_reply_without_structured_output_is_an_error():
    with pytest.raises(ClaudeError, match="structured_output"):
        ask_claude("hi", json_schema=SCHEMA, run=fake_run(json.dumps(GOOD)))
