"""Contract test for the progress_store block: its ID card and SPEC.md are complete.

Plus behaviour tests from SPEC.md (ADR 0013), on real SQLite files in tmp_path,
with toy capitals cards only.
"""

import re
import sqlite3
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

import quizkit.blocks.progress_store as block
from quizkit.blocks.base import missing_spec_sections, spec_section

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "progress_store"
    assert block.BLOCK_SPEC.kind == "script"


def test_spec_md_has_every_section():
    assert missing_spec_sections(SPEC_MD) == []


def test_inputs_and_outputs_match_spec():
    """The code's ID card (BLOCK_SPEC) and the job description (SPEC.md) agree."""
    for field, section in [("inputs", "Inputs"), ("outputs", "Outputs")]:
        listed = getattr(block.BLOCK_SPEC, field)
        text = spec_section(SPEC_MD, section)
        for item in listed:
            assert item in text, (
                f"BLOCK_SPEC.{field} has {item!r}, not in SPEC.md {section}"
            )
        if "TODO" not in text:  # once the SPEC section is filled in...
            assert listed, (
                f"SPEC.md {section} is filled in: copy it into BLOCK_SPEC.{field}"
            )


# --- Behaviour tests (from SPEC.md) -----------------------------------------------
# Public names are looked up on `block` inside each test, so the contract tests
# above still run while the block is unbuilt.

T0 = datetime(2026, 11, 10, 9, 0, 0, tzinfo=UTC)
PLUS8 = timezone(timedelta(hours=8))
NAIVE = datetime(2026, 11, 10, 9, 0, 0)


def answer(card_id="france", skill="recall", at=T0, **kw):
    fields = {
        "at": at,
        "card_id": card_id,
        "skill": skill,
        "mode": "capital",
        "typed": "Paris",
        "correct": True,
        "decided_by": "grader",
    }
    return block.AnswerRecord(**(fields | kw))


def note(card_id="france", skill="recall", box=2, at=T0, **kw):
    fields = {
        "card_id": card_id,
        "skill": skill,
        "box": box,
        "due": at + timedelta(days=1),
        "last_seen": at,
        "right": 1,
        "wrong": 0,
    }
    return block.BoxState(**(fields | kw))


@pytest.fixture
def db(tmp_path):
    return tmp_path / "progress.db"


@pytest.fixture
def store(db):
    return block.ProgressStore(db)


# Round trip


def test_answer_and_box_read_back_exactly(store):
    a, b = answer(), note()
    store.record(a, b)
    assert store.answers() == [a]
    assert store.box("france", "recall") == b


def test_times_read_back_as_same_instant_in_utc(store):
    at = datetime(2026, 11, 10, 17, 0, 0, tzinfo=PLUS8)  # 09:00 UTC
    store.record(answer(at=at), note(at=at))
    got_a = store.answers()[0]
    got_b = store.box("france", "recall")
    assert got_a.at == at
    assert got_b.last_seen == at and got_b.due == at + timedelta(days=1)
    for t in (got_a.at, got_b.due, got_b.last_seen):
        assert t.utcoffset() == timedelta(0)


def test_new_note_replaces_old_note_for_same_card_and_skill(store):
    store.record(answer(), note(box=2))
    newer = note(box=3, at=T0 + timedelta(days=1), right=2)
    store.record(answer(at=T0 + timedelta(days=1)), newer)
    assert store.box("france", "recall") == newer
    assert store.boxes("recall") == {"france": newer}
    assert len(store.answers()) == 2  # every answer is kept


def test_notes_for_two_skills_stay_apart(store):
    recall = note(skill="recall", box=3)
    spell = note(skill="spell", box=1, right=0, wrong=1)
    store.record(answer(skill="recall"), recall)
    store.record(answer(skill="spell", correct=False), spell)
    assert store.box("france", "recall") == recall
    assert store.box("france", "spell") == spell
    assert store.boxes("recall") == {"france": recall}
    assert store.boxes("spell") == {"france": spell}


def test_boxes_returns_every_note_for_a_skill(store):
    fr, jp = note("france"), note("japan", box=4)
    store.record(answer("france"), fr)
    store.record(answer("japan", typed="Tokyo"), jp)
    store.record(answer("peru", skill="spell"), note("peru", skill="spell"))
    assert store.boxes("recall") == {"france": fr, "japan": jp}


def test_blank_typed_answer_is_saved(store):
    a = answer(typed="", correct=False, decided_by="not_checked")
    store.record(a, None)
    assert store.answers() == [a]


# box=None


def test_box_none_saves_answer_and_keeps_old_note(store):
    old = note(box=3)
    store.record(answer(), old)
    later = answer(at=T0 + timedelta(hours=1), decided_by="not_checked")
    store.record(later, None)
    assert store.box("france", "recall") == old
    assert store.answers()[-1] == later


def test_box_none_on_new_card_leaves_no_note(store):
    store.record(answer(), None)
    assert store.box("france", "recall") is None
    assert store.boxes("recall") == {}
    assert len(store.answers()) == 1


# Never seen


def test_unseen_card_has_no_box(store):
    assert store.box("france", "recall") is None


def test_skill_with_no_notes_gives_empty_dict(store):
    store.record(answer(), note())
    assert store.boxes("spell") == {}


# Reopening and making the file


def test_reopening_the_file_finds_everything(db):
    a, b = answer(), note()
    block.ProgressStore(db).record(a, b)
    again = block.ProgressStore(db)
    assert again.answers() == [a]
    assert again.box("france", "recall") == b


def test_missing_folder_and_file_are_made(tmp_path):
    path = tmp_path / "deep" / "er" / "progress.db"
    store = block.ProgressStore(path)
    assert path.exists()
    assert store.answers() == []


def test_file_has_both_tables_and_schema_version_1(db):
    block.ProgressStore(db)
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    version = con.execute("PRAGMA user_version").fetchone()[0]
    con.close()
    assert {"answers", "boxes"} <= tables
    assert version == 1


# answers()


def test_empty_store_has_no_answers(store):
    assert store.answers() == []


def test_answers_are_oldest_first(store):
    times = [T0 + timedelta(minutes=m) for m in (5, 0, 10)]
    for t in times:  # saved out of order on purpose
        store.record(answer(at=t), None)
    assert [a.at for a in store.answers()] == sorted(times)


def test_since_keeps_answers_at_or_after_the_time(store):
    for m in (0, 5, 10):
        store.record(answer(at=T0 + timedelta(minutes=m)), None)
    got = store.answers(since=T0 + timedelta(minutes=5))
    assert [a.at for a in got] == [
        T0 + timedelta(minutes=5),
        T0 + timedelta(minutes=10),
    ]


def test_since_in_another_timezone_compares_instants(store):
    store.record(answer(at=T0), None)
    store.record(answer(at=T0 + timedelta(hours=2)), None)
    since = datetime(2026, 11, 10, 18, 0, tzinfo=PLUS8)  # 10:00 UTC
    assert [a.at for a in store.answers(since=since)] == [T0 + timedelta(hours=2)]


def test_skill_filters_answers(store):
    store.record(answer(skill="recall"), None)
    store.record(answer(skill="spell", at=T0 + timedelta(minutes=1)), None)
    assert [a.skill for a in store.answers(skill="spell")] == ["spell"]


def test_since_and_skill_filter_together(store):
    store.record(answer(skill="spell", at=T0), None)
    store.record(answer(skill="recall", at=T0 + timedelta(minutes=2)), None)
    store.record(answer(skill="spell", at=T0 + timedelta(minutes=3)), None)
    got = store.answers(since=T0 + timedelta(minutes=1), skill="spell")
    assert [(a.skill, a.at) for a in got] == [("spell", T0 + timedelta(minutes=3))]


# All or nothing


def test_failed_box_write_saves_neither_answer_nor_note(db, store):
    """A trigger makes the box write fail inside SQLite, halfway through record."""
    con = sqlite3.connect(db)
    for event in ("INSERT", "UPDATE"):
        con.execute(
            f"CREATE TRIGGER fail_{event.lower()} BEFORE {event} ON boxes "
            "BEGIN SELECT RAISE(ABORT, 'box write failed'); END"
        )
    con.commit()
    con.close()
    with pytest.raises(block.ProgressFileError, match="nothing was saved"):
        store.record(answer(), note())
    assert store.answers() == []
    assert store.box("france", "recall") is None


# Errors


def test_progress_file_error_is_a_value_error():
    assert issubclass(block.ProgressFileError, ValueError)


def test_text_file_posing_as_database_raises_and_is_kept(db):
    text = "Paris is the capital of France.\n" * 50
    db.write_text(text, encoding="utf-8")
    with pytest.raises(block.ProgressFileError, match=re.escape(db.name)):
        block.ProgressStore(db)
    assert db.read_text(encoding="utf-8") == text


def test_damaged_database_raises_progress_file_error(db):
    block.ProgressStore(db).record(answer(), note())
    data = bytearray(db.read_bytes())
    data[:100] = b"\x00" * 100  # wipe the header
    db.write_bytes(bytes(data))
    with pytest.raises(block.ProgressFileError, match=re.escape(db.name)):
        block.ProgressStore(db)
    assert db.read_bytes() == bytes(data)


def test_newer_schema_version_raises_and_changes_nothing(db):
    con = sqlite3.connect(db)
    con.execute("PRAGMA user_version = 2")
    con.commit()
    con.close()
    before = db.read_bytes()
    with pytest.raises(
        block.ProgressFileError, match=re.compile("newer|version", re.IGNORECASE)
    ):
        block.ProgressStore(db)
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "mismatch", [{"card_id": "japan"}, {"skill": "spell"}], ids=["card", "skill"]
)
def test_box_for_another_card_or_skill_raises_before_saving(store, mismatch):
    with pytest.raises(ValueError):
        store.record(answer(), note(**mismatch))
    assert store.answers() == []
    assert store.box("france", "recall") is None
    assert store.box(mismatch.get("card_id", "france"), "recall") is None
    assert store.boxes("spell") == {}


def test_file_locked_too_long_raises_busy_and_saves_nothing(db):
    """Another connection holds an exclusive lock (a short wait, so the test is quick)."""
    store = block.ProgressStore(db, busy_seconds=0.5)
    other = sqlite3.connect(db, isolation_level=None)
    other.execute("BEGIN EXCLUSIVE")
    try:
        start = time.monotonic()
        with pytest.raises(
            block.ProgressFileError, match=re.compile("busy", re.IGNORECASE)
        ):
            store.record(answer(), note())
        assert time.monotonic() - start >= 0.4  # it waited, didn't give up at once
    finally:
        other.execute("ROLLBACK")
        other.close()
    assert store.answers() == []


# Model checks (pydantic ValidationError when the model is made)


@pytest.mark.parametrize(
    "bad",
    [
        {"at": NAIVE},
        {"card_id": ""},
        {"card_id": "   "},
        {"skill": ""},
        {"skill": "  "},
        {"mode": ""},
        {"mode": " \t"},
        {"decided_by": "teacher"},
    ],
)
def test_answer_record_rejects_bad_fields(bad):
    with pytest.raises(ValidationError):
        answer(**bad)


@pytest.mark.parametrize(
    "decided_by", ["grader", "typo", "claude", "cache", "self", "not_checked"]
)
def test_answer_record_accepts_every_decider(decided_by):
    assert answer(decided_by=decided_by).decided_by == decided_by


@pytest.mark.parametrize(
    "bad",
    [
        {"due": NAIVE},
        {"last_seen": NAIVE},
        {"card_id": ""},
        {"skill": " "},
        {"box": 0},
        {"box": -1},
        {"right": -1},
        {"wrong": -1},
    ],
)
def test_box_state_rejects_bad_fields(bad):
    with pytest.raises(ValidationError):
        note(**bad)


def test_models_are_frozen():
    a, b = answer(), note()
    with pytest.raises(ValidationError):
        a.correct = False
    with pytest.raises(ValidationError):
        b.box = 5


# Generic

CJK = re.compile(r"[㐀-鿿豈-﫿]")


def test_block_code_has_no_chinese():
    for py in Path(block.__file__).parent.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert not CJK.search(text), f"{py.name}: {CJK.findall(text)}"
        # the word "Chinese" may appear in a docstring saying the block is generic
        assert not re.search(r"hsk|mandarin|pinyin", text, re.IGNORECASE), py.name


def test_default_busy_wait_is_five_seconds(db):
    assert block.ProgressStore(db).busy_seconds == 5.0


def test_microseconds_survive_the_round_trip(store):
    from datetime import UTC, datetime

    when = datetime(2026, 11, 10, 9, 30, 15, 123456, tzinfo=UTC)
    store.record(answer().model_copy(update={"at": when}), None)
    assert store.answers()[0].at == when


def test_same_time_answers_come_back_in_save_order(store):
    first = answer().model_copy(update={"typed": "first"})
    second = first.model_copy(update={"typed": "second"})
    store.record(first, None)
    store.record(second, None)
    assert [a.typed for a in store.answers()] == ["first", "second"]


def test_since_without_a_timezone_is_a_value_error(store):
    from datetime import datetime

    with pytest.raises(ValueError):
        store.answers(since=datetime(2026, 1, 1))


def test_someone_elses_database_is_not_taken_over(tmp_path):
    import sqlite3

    other = tmp_path / "other.db"
    with sqlite3.connect(other) as con:
        con.execute("CREATE TABLE answers (question TEXT)")
    before = other.read_bytes()
    with pytest.raises(block.ProgressFileError):
        block.ProgressStore(other)
    assert other.read_bytes() == before


def test_hand_edited_bad_row_is_a_progress_file_error(db, store):
    import sqlite3

    store.record(answer(), note())
    with sqlite3.connect(db) as con:
        con.execute("UPDATE boxes SET box = 0")
        con.execute("UPDATE answers SET decided_by = 'human'")
    for read in (
        lambda: store.box("france", "recall"),
        lambda: store.boxes("recall"),
        lambda: store.answers(),
    ):
        with pytest.raises(block.ProgressFileError, match="row"):
            read()


def test_reads_never_say_nothing_was_saved(db):
    import sqlite3

    store = block.ProgressStore(db, busy_seconds=0.2)
    other = sqlite3.connect(db, isolation_level=None)
    other.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(block.ProgressFileError) as caught:
            store.answers()
    finally:
        other.execute("ROLLBACK")
        other.close()
    assert "busy" in str(caught.value)
    assert "saved" not in str(caught.value)


def test_skill_reads_have_an_index(db, store):
    import sqlite3

    with sqlite3.connect(db) as con:
        plans = [
            " ".join(str(c) for c in row)
            for sql in (
                "EXPLAIN QUERY PLAN SELECT * FROM boxes WHERE skill = 'recall'",
                "EXPLAIN QUERY PLAN SELECT * FROM answers WHERE skill = 'recall'",
            )
            for row in con.execute(sql)
        ]
    assert all("SCAN" not in p or "INDEX" in p for p in plans), plans
