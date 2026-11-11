"""The web quiz page (ADR 0014), run in-process by Streamlit's AppTest (no browser).

The page is thin, so these check the wiring: the buttons reach the brain, and each
screen shows what it says. One-word cards files keep the deck predictable.
"""

import json
import re
import sys
from typing import ClassVar

import pytest
from streamlit.testing.v1 import AppTest
from typer.testing import CliRunner

from hsk_trainer import cli
from hsk_trainer.quiz_setup import CARDS_FILE, ROOT, QuizFiles
from hsk_trainer.web_quiz import WebQuiz
from quizkit.models import Verdict

COULDNT = Verdict(correct=False, reason="is offline", source="not_checked")


class Offline:
    """A judge that can't check, so the translate modes ask for your own mark."""

    def __init__(self, subject, **kwargs):
        pass

    def __call__(self, question, typed):
        return COULDNT


def page(tmp_path, ids=("爱",)):
    lines = [
        line
        for line in CARDS_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
        if json.loads(line)["id"] in ids
    ]
    cards = tmp_path / "cards.jsonl"
    cards.write_text("".join(lines), encoding="utf-8")
    files = QuizFiles(cards=cards, seen=tmp_path / "seen.json")
    at = AppTest.from_file(str(cli.WEB_PAGE), default_timeout=30)
    at.session_state["quiz"] = WebQuiz(judge_class=Offline, files=files)
    at.run()
    at.checkbox(key="live").uncheck()
    return at


def button(at, label):
    return next(b for b in at.button if b.label == label)


def shown(text):
    """As the browser shows it: the page escapes Markdown with backslashes."""
    return re.sub(r"\\(.)", r"\1", text)


def texts(at):
    return shown(
        " | ".join(
            [e.value for e in at.markdown]
            + [e.value for e in at.caption]
            + [e.value for e in at.text]
            + [e.value for e in at.success]
            + [e.value for e in at.error]
            + [e.value for e in at.info]
        )
    )


def test_page_opens_on_the_settings(tmp_path):
    at = page(tmp_path)
    assert not at.exception
    assert at.title[0].value == "HSK Trainer"
    assert at.button(key="start").label == "Start quiz"
    assert at.selectbox(key="mode").value == "char"


def test_a_word_quiz_from_start_to_new_quiz(tmp_path):
    at = page(tmp_path)
    at.button(key="start").click().run()
    assert not at.exception
    assert at.subheader[0].value == "Word 1 of 1"
    assert at.selectbox(key="mode").disabled  # settings locked while it runs
    assert "爱" in texts(at)

    at.text_input(key="typed-1").input("love")
    button(at, "Check").click().run()
    assert (at.success[0].icon, at.success[0].value) == ("✅", "Right")
    assert "You wrote: love" in texts(at)

    at.button(key="next-1").click().run()
    assert at.subheader[0].value == "Done"
    assert "Score: 1/1" in texts(at)

    at.button(key="new").click().run()
    assert at.button(key="start").label == "Start quiz"
    assert not at.selectbox(key="mode").disabled


def test_wrong_answer_shows_the_answers(tmp_path):
    at = page(tmp_path)
    at.checkbox(key="judge").uncheck()
    at.button(key="start").click().run()
    at.text_input(key="typed-1").input("banana")
    button(at, "Check").click().run()
    assert at.error[0].icon == "❌"
    assert at.error[0].value.startswith("love")  # the accepted answers


def test_a_translate_quiz_asks_did_you_get_the_gist(tmp_path):
    at = page(tmp_path)
    at.selectbox(key="mode").set_value("translate")
    at.button(key="start").click().run()
    assert at.subheader[0].value == "Sentence 1 of 1"

    at.text_input(key="typed-1").input("something else")
    button(at, "Check").click().run()
    assert not at.exception
    assert at.info[0].value.startswith("= ")  # the English, before you mark it
    assert "(the judge couldn't check: is offline)" in texts(at)

    at.button(key="yes-1").click().run()
    assert (at.success[0].icon, at.success[0].value) == ("✅", "you got the gist")
    at.button(key="next-1").click().run()
    assert "Score: 1/1" in texts(at)


def test_stop_ends_the_quiz(tmp_path):
    at = page(tmp_path, ids=("爱", "八"))
    at.button(key="start").click().run()
    at.button(key="stop").click().run()
    assert at.subheader[0].value == "Done"
    assert "Stopped after 0 of 2." in texts(at)


def test_a_setup_problem_is_shown_on_the_page(tmp_path):
    at = AppTest.from_file(str(cli.WEB_PAGE), default_timeout=30)
    at.session_state["quiz"] = WebQuiz(files=QuizFiles(cards=tmp_path / "none.jsonl"))
    at.run()
    at.button(key="start").click().run()
    assert shown(at.error[0].value).startswith("No cards file at")
    # A Windows path keeps its backslashes once drawn (Markdown would eat them).
    assert str(tmp_path / "none.jsonl") in shown(at.error[0].value)


# --- hsk web ------------------------------------------------------------------------


class FakeStreamlit:
    """Stands in for the Streamlit process: `hsk web` must not start the real one."""

    started: ClassVar[list] = []

    def __init__(self, command, code=0, stops_early=False, interrupted=False, **kw):
        self.command, self.kwargs, self.code = command, kw, code
        self.stops_early, self.interrupted = stops_early, interrupted
        FakeStreamlit.started.append(self)

    def poll(self):
        return self.code if self.stops_early else None

    def wait(self, timeout=None):
        if self.interrupted:
            self.interrupted = False  # Ctrl-C once, then Streamlit finishes
            raise KeyboardInterrupt
        return self.code

    def kill(self):  # pragma: no cover - only if Streamlit hangs after Ctrl-C
        pass


@pytest.fixture
def streamlit(monkeypatch):
    """`hsk web` with Streamlit, the browser and the address check all faked."""
    FakeStreamlit.started = []
    opened, answers = [], []
    monkeypatch.setattr(cli, "webbrowser", type("W", (), {"open": opened.append}))
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)

    def web_is_up():
        return answers.pop(0) if answers else True

    monkeypatch.setattr(cli, "_web_is_up", web_is_up)

    def run(*up, **process):
        answers.extend(up)
        monkeypatch.setattr(
            cli.subprocess, "Popen", lambda c, **k: FakeStreamlit(c, **process, **k)
        )
        return CliRunner().invoke(cli.app, ["web"]), opened

    return run


def test_hsk_web_starts_streamlit_headless_and_opens_the_page(streamlit):
    result, opened = streamlit(False, True)  # not running yet, then up
    assert result.exit_code == 0
    [process] = FakeStreamlit.started
    command = process.command
    assert command[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert command[4] == str(cli.WEB_PAGE) and cli.WEB_PAGE.exists()
    assert "--server.address=localhost" in command  # this computer only
    assert "--browser.gatherUsageStats=false" in command
    assert "--client.toolbarMode=minimal" in command  # no Deploy button
    # Headless: no first-run email question (it crashed `hsk web` without a keyboard).
    assert "--server.headless=true" in command
    assert f"--server.port={cli.WEB_PORT}" in command
    assert process.kwargs["cwd"] == ROOT
    assert opened == [cli.WEB_URL] == ["http://localhost:8501"]
    assert cli.WEB_URL in result.output


def test_hsk_web_when_something_already_runs_there(streamlit):
    result, opened = streamlit(True)
    assert result.exit_code == 1
    assert FakeStreamlit.started == [] and opened == []
    assert "already running at http://localhost:8501" in result.output


def test_hsk_web_streamlit_failing_to_start_opens_nothing(streamlit):
    result, opened = streamlit(False, False, code=1, stops_early=True)
    assert result.exit_code == 1
    assert opened == []


def test_hsk_web_ctrl_c_is_a_clean_stop(streamlit):
    result, _ = streamlit(False, True, interrupted=True)
    assert result.exit_code == 0


def test_streamlit_config_keeps_it_local():
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'address = "localhost"' in config
    assert "gatherUsageStats = false" in config
    assert 'toolbarMode = "minimal"' in config
    assert "headless = true" in config
    assert "port = 8501" in config


def test_every_mode_has_a_plain_label_and_hint():
    """The menu says what you see and what you type, not the code's name."""
    from hsk_trainer.modes import MODE_LABELS, mode_hint
    from hsk_trainer.quiz_setup import PLAYABLE_MODES

    assert set(MODE_LABELS) == set(PLAYABLE_MODES)
    assert all(MODE_LABELS[m].startswith("Words:") for m in PLAYABLE_MODES[:4])
    assert MODE_LABELS["translate"].startswith("Sentences:")
    assert "whole sentence" in mode_hint("translate")
    assert "word's meaning" in mode_hint("char_sentence")


def test_mode_menu_shows_the_labels(tmp_path):
    at = page(tmp_path)
    assert at.selectbox(key="mode").options[:1] == ["Words: the character"]
    at.selectbox(key="mode").set_value("translate").run()
    assert "whole sentence" in texts(at)
