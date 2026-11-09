"""progress_store: Save every answer and each card's Leitner box for each skill, and read them back.

See SPEC.md in this folder (ADR 0003, ADR 0013). A filing cabinet: it never decides a
box (the Leitner rule does) and knows nothing about Chinese. One SQLite file, one
transaction per answer, so an answer and its box note are saved together or not at all.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from quizkit.blocks.base import BlockSpec

BLOCK_SPEC = BlockSpec(
    name="progress_store",
    kind="script",
    goal="Save every answer and each card's Leitner box for each skill, and read them back.",
    inputs=["path", "answer", "box", "card_id", "skill", "since", "busy_seconds"],
    outputs=["AnswerRecord", "BoxState"],
)

__all__ = [
    "BLOCK_SPEC",
    "SCHEMA_VERSION",
    "AnswerRecord",
    "BoxState",
    "DecidedBy",
    "ProgressFileError",
    "ProgressStore",
]

SCHEMA_VERSION = 1
BUSY_SECONDS = 5.0  # wait this long for a file another program has locked
_TIME = "%Y-%m-%dT%H:%M:%S.%f+00:00"  # one fixed width, so the text sorts by time

DecidedBy = Literal["grader", "typo", "claude", "cache", "self", "not_checked"]


class ProgressFileError(ValueError):
    """The progress file can't be used (not a database, too new, or busy)."""


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class AnswerRecord(BaseModel):
    """One answer, as the quiz scored it."""

    model_config = ConfigDict(frozen=True)

    at: AwareDatetime
    card_id: str
    skill: str
    mode: str
    typed: str
    correct: bool
    decided_by: DecidedBy

    _check_names = field_validator("card_id", "skill", "mode")(_not_blank)


class BoxState(BaseModel):
    """One card's note for one skill: its box, when it's due, and its tally."""

    model_config = ConfigDict(frozen=True)

    card_id: str
    skill: str
    box: int = Field(ge=1)
    due: AwareDatetime
    last_seen: AwareDatetime
    right: int = Field(ge=0)
    wrong: int = Field(ge=0)

    _check_names = field_validator("card_id", "skill")(_not_blank)


def _text(when: datetime) -> str:
    return when.astimezone(UTC).strftime(_TIME)


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    card_id TEXT NOT NULL,
    skill TEXT NOT NULL,
    mode TEXT NOT NULL,
    typed TEXT NOT NULL,
    correct INTEGER NOT NULL,
    decided_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS answers_at ON answers (at);
CREATE INDEX IF NOT EXISTS answers_skill_at ON answers (skill, at);
CREATE TABLE IF NOT EXISTS boxes (
    card_id TEXT NOT NULL,
    skill TEXT NOT NULL,
    box INTEGER NOT NULL,
    due TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    right INTEGER NOT NULL,
    wrong INTEGER NOT NULL,
    PRIMARY KEY (skill, card_id)
);
"""


class ProgressStore:
    """The filing cabinet: answers and box notes in one SQLite file."""

    def __init__(self, path: Path, busy_seconds: float = BUSY_SECONDS) -> None:
        self.path = Path(path)
        self.busy_seconds = busy_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._open("open") as con:
            # One write-locked transaction, so two quizzes opening a new file at once
            # can't see each other half-way; tables and version go in together.
            con.execute("BEGIN IMMEDIATE")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                con.rollback()
                return
            if version > SCHEMA_VERSION:
                con.rollback()
                raise ProgressFileError(
                    f"{self.path} was made by a newer version (schema {version}, "
                    f"this one reads {SCHEMA_VERSION}); nothing was changed"
                )
            # Only version 0 can be new; an older schema would need an upgrade step
            # here (none exists yet: this is schema 1).
            tables = con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            if tables:  # someone else's database: don't take it over
                con.rollback()
                raise ProgressFileError(
                    f"{self.path} is another program's database (it has "
                    f"{', '.join(t[0] for t in tables)}); it was left as it is"
                )
            for statement in _SCHEMA.split(";"):
                if statement.strip():
                    con.execute(statement)
            con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            con.commit()

    @contextmanager
    def _open(self, doing: str) -> Iterator[sqlite3.Connection]:
        """A connection; SQLite problems become a ProgressFileError naming the file
        and what was being done (`doing`: "open", "save to" or "read")."""
        after = "; nothing was saved" if doing == "save to" else ""
        try:
            with closing(sqlite3.connect(self.path, timeout=self.busy_seconds)) as con:
                yield con
        except sqlite3.Error as err:
            name = getattr(err, "sqlite_errorname", "") or ""
            if name.startswith(("SQLITE_BUSY", "SQLITE_LOCKED")):
                raise ProgressFileError(
                    f"{self.path} is busy (another program has it open){after}"
                ) from err
            if name.startswith(("SQLITE_NOTADB", "SQLITE_CORRUPT")):
                raise ProgressFileError(
                    f"{self.path} isn't a progress file ({err}); it was left as it is"
                ) from err
            raise ProgressFileError(f"can't {doing} {self.path}: {err}{after}") from err

    def _read_row(self, make, *args):
        """Build a model from a saved row; a bad row is a ProgressFileError."""
        try:
            return make(*args)
        except ValidationError as err:
            raise ProgressFileError(
                f"{self.path} has a row that can't be read (edited by hand?): {err}"
            ) from err

    def record(self, answer: AnswerRecord, box: BoxState | None) -> None:
        """Save the answer and (unless None) the card's new box note, together."""
        if box is not None and (box.card_id, box.skill) != (
            answer.card_id,
            answer.skill,
        ):
            raise ValueError(
                f"the box note is for {box.card_id!r} / {box.skill!r}, but the answer "
                f"is for {answer.card_id!r} / {answer.skill!r}"
            )
        with self._open("save to") as con, con:  # `with con`: all or nothing
            self._save_answer(con, answer)
            if box is not None:
                self._save_box(con, box)

    @staticmethod
    def _save_answer(con: sqlite3.Connection, answer: AnswerRecord) -> None:
        con.execute(
            "INSERT INTO answers (at, card_id, skill, mode, typed, correct, decided_by)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                _text(answer.at),
                answer.card_id,
                answer.skill,
                answer.mode,
                answer.typed,
                int(answer.correct),
                answer.decided_by,
            ),
        )

    @staticmethod
    def _save_box(con: sqlite3.Connection, box: BoxState) -> None:
        con.execute(
            "INSERT OR REPLACE INTO boxes"
            " (card_id, skill, box, due, last_seen, right, wrong)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                box.card_id,
                box.skill,
                box.box,
                _text(box.due),
                _text(box.last_seen),
                box.right,
                box.wrong,
            ),
        )

    @staticmethod
    def _box_from(row: tuple) -> BoxState:
        card_id, skill, box, due, last_seen, right, wrong = row
        return BoxState(
            card_id=card_id,
            skill=skill,
            box=box,
            due=_time(due),
            last_seen=_time(last_seen),
            right=right,
            wrong=wrong,
        )

    def box(self, card_id: str, skill: str) -> BoxState | None:
        """The card's note for this skill, or None if it was never answered."""
        with self._open("read") as con:
            row = con.execute(
                "SELECT card_id, skill, box, due, last_seen, right, wrong FROM boxes"
                " WHERE card_id = ? AND skill = ?",
                (card_id, skill),
            ).fetchone()
        return None if row is None else self._read_row(self._box_from, row)

    def boxes(self, skill: str) -> dict[str, BoxState]:
        """Every card's note for this skill, by card id."""
        with self._open("read") as con:
            rows = con.execute(
                "SELECT card_id, skill, box, due, last_seen, right, wrong FROM boxes"
                " WHERE skill = ?",
                (skill,),
            ).fetchall()
        return {row[0]: self._read_row(self._box_from, row) for row in rows}

    def answers(
        self, since: datetime | None = None, skill: str | None = None
    ) -> list[AnswerRecord]:
        """Saved answers, oldest first; only from `since` on and for `skill`, if given."""
        if since is not None and since.tzinfo is None:
            raise ValueError("since must have a timezone (e.g. datetime.now(UTC))")
        query = (
            "SELECT at, card_id, skill, mode, typed, correct, decided_by FROM answers"
        )
        where, args = [], []
        if since is not None:
            where.append("at >= ?")
            args.append(_text(since))
        if skill is not None:
            where.append("skill = ?")
            args.append(skill)
        if where:
            query += " WHERE " + " AND ".join(where)
        with self._open("read") as con:
            rows = con.execute(query + " ORDER BY at, id", args).fetchall()
        return [self._read_row(self._answer_from, row) for row in rows]

    @staticmethod
    def _answer_from(row: tuple) -> AnswerRecord:
        at, card_id, row_skill, mode, typed, correct, decided_by = row
        return AnswerRecord(
            at=_time(at),
            card_id=card_id,
            skill=row_skill,
            mode=mode,
            typed=typed,
            correct=bool(correct),
            decided_by=decided_by,
        )
