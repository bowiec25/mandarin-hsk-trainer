"""The web Stats page (ADR 0014), run in-process by Streamlit's AppTest (no browser).

The numbers come from quiz_setup.gather_stats (tested in test_quiz_setup.py); these
check the page shows them, filters by band, and never makes the progress file.
"""

from datetime import UTC, datetime, timedelta

from streamlit.testing.v1 import AppTest

from hsk_trainer import cli
from hsk_trainer.quiz_setup import QuizFiles
from quizkit.blocks.progress_store import AnswerRecord, BoxState, ProgressStore

STATS_PAGE = cli.WEB_PAGE.with_name("web_pages") / "stats.py"


def files_in(tmp_path):
    return QuizFiles(progress=tmp_path / "progress.db", seen=tmp_path / "seen.json")


def save(files, word="爱", correct=True, box=2):
    now = datetime.now(UTC)
    ProgressStore(files.progress).record(
        AnswerRecord(
            at=now,
            card_id=word,
            skill="recognise",
            mode="char",
            typed="x",
            correct=correct,
            decided_by="grader",
        ),
        BoxState(
            card_id=word,
            skill="recognise",
            box=box,
            due=now + timedelta(days=1),
            last_seen=now,
            right=int(correct),
            wrong=int(not correct),
        ),
    )


def page(files):
    at = AppTest.from_file(str(STATS_PAGE), default_timeout=30)
    at.session_state["stats_files"] = files
    return at.run()


def texts(at):
    return " | ".join(
        [e.value for e in at.markdown]
        + [e.value for e in at.caption]
        + [e.value for e in at.header]
        + [e.value for e in at.subheader]
        + [e.value for e in at.info]
        + [e.value for e in at.error]
    ).replace("\\", "")


def test_no_progress_says_so_and_makes_no_file(tmp_path):
    files = files_in(tmp_path)
    at = page(files)
    assert not at.exception
    assert "No progress saved yet" in at.info[0].value
    assert not files.progress.exists()


def test_shows_the_numbers_after_some_answers(tmp_path):
    files = files_in(tmp_path)
    save(files, "爱", correct=False, box=1)
    save(files, "吃", correct=True, box=2)
    at = page(files)
    assert not at.exception
    shown = texts(at)
    assert all(f"Band {b} · " in shown for b in (1, 2, 3))
    assert "recognise (char, char_pinyin, char_sentence, full)" in shown
    assert "box 1: 1 · box 2: 1 · box 3: 0" in shown
    assert "Last 7 days: 1/2 right (50%)" in shown
    assert "Nothing yet." in shown  # the sentence skill, and bands 2-3
    week = next(m for m in at.metric if m.label == "Last 7 days")
    assert week.value == "50%"
    missed = at.dataframe[0].value
    assert list(missed["Word"]) == ["爱 ài"]
    assert list(missed["Missed"]) == [1]


def test_band_menu_shows_one_band(tmp_path):
    files = files_in(tmp_path)
    save(files)
    at = page(files)
    at.selectbox(key="stats_band").select(1).run()
    shown = texts(at)
    assert "Band 1 · " in shown
    assert "Band 2" not in shown


def test_a_broken_progress_file_is_an_error_box_not_a_crash(tmp_path):
    files = files_in(tmp_path)
    files.progress.write_bytes(b"not a database at all, just text" * 10)
    at = page(files)
    assert not at.exception
    assert "progress file" in at.error[0].value


def test_the_app_has_a_stats_page_in_its_menu(tmp_path):
    """The entry (web_app.py) opens on the quiz; its Stats page is the file above."""
    at = AppTest.from_file(str(cli.WEB_PAGE), default_timeout=30)
    at.session_state["stats_files"] = files_in(tmp_path)
    at.run()
    assert not at.exception
    assert at.selectbox(key="band")  # the quiz page's settings
    at.switch_page("web_pages/stats.py").run()
    assert not at.exception
    assert "No progress saved yet" in at.info[0].value


def test_quiz_settings_survive_a_visit_to_stats(tmp_path):
    """Code review: Streamlit forgets an undrawn widget's value; the entry keeps it."""
    at = AppTest.from_file(str(cli.WEB_PAGE), default_timeout=30)
    at.session_state["stats_files"] = files_in(tmp_path)
    at.run()
    at.selectbox(key="band").select(3).run()
    at.number_input(key="n").set_value(25).run()
    at.switch_page("web_pages/stats.py").run()
    at.switch_page("web_pages/quiz.py").run()
    assert not at.exception
    assert at.selectbox(key="band").value == 3
    assert at.number_input(key="n").value == 25
