# Block: `progress_store`

> **In plain words:** Save every answer and each card's Leitner box for each skill, and read them back.

## Goal
Save every answer and each card's Leitner box for each skill, and read them back.

It is a **filing cabinet** (ADR 0013). It keeps two drawers: every answer ever given, and one note per card and skill saying which box it's in and when it's next due. It **never decides** anything: the Leitner rule (`next_box`, the next PR) works out the new box, and the caller hands it over to be filed. It knows nothing about Chinese: a capitals quiz could use it unchanged.

**Not in scope:** the box rule, choosing which cards come next (`deck_builder`), stats wording (`hsk stats`).

## Kind
**script.** Code can check every result: what you save is exactly what you read back, an answer and its box note are saved together or not at all, and a broken file gives a clear error. No judgment (ADR 0002). It runs on every answer, so it must be quick (one small write) and needs no network.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `path` | `Path` | The SQLite file, e.g. `data/progress.db` (the caller chooses; this block has no default, so it stays generic). Made, with its folder, if missing |
| `answer` | `AnswerRecord` | One answer to save (see Outputs for its fields) |
| `box` | `BoxState \| None` | The card's new box note for that skill, worked out by the caller. `None` = leave the box as it is (e.g. an answer nobody could check, ADR 0013) |
| `card_id`, `skill` | `str` | Which note to read back |
| `since` | `datetime \| None` | Only answers at or after this time (timezone-aware; one without a timezone is a `ValueError`). `None` = all |
| `busy_seconds` | `float` | How long to wait for a file another program has locked. Default `5.0`; tests pass less |

**How it's called** (all importable from `quizkit.blocks.progress_store`):
```python
store = ProgressStore(path, busy_seconds=5.0)  # opens (or makes) the file
store.record(answer, box)  # saves both in one go (box may be None)
store.box(card_id, skill)  # -> BoxState | None (None = never seen)
store.boxes(skill)  # -> dict[card_id, BoxState], every note for a skill
store.answers(since=None, skill=None)  # -> list[AnswerRecord], oldest first
```
Each call opens the file and closes it again, so there is nothing to close and the file is never held open between answers (on Windows another program, or a second quiz, can still use it).

## Outputs
Both are frozen pydantic models. Every time is **timezone-aware** and saved as UTC, to the microsecond, so it reads back as the same instant. "Oldest first" = by `at`; answers with the same `at` come back in the order they were saved.

**`AnswerRecord`**: one answer
| Field | Type | Plain meaning |
|---|---|---|
| `at` | `datetime` | When it was marked |
| `card_id` | `str` | Which card (not blank) |
| `skill` | `str` | Which skill, from the mode's config (e.g. `recognise`, `sentence`; not blank) |
| `mode` | `str` | Which mode it was asked in (not blank) |
| `typed` | `str` | Exactly what was typed (may be blank) |
| `correct` | `bool` | Right or wrong, as the quiz scored it |
| `decided_by` | `"grader" \| "typo" \| "claude" \| "cache" \| "self" \| "not_checked"` | Who decided |

**`BoxState`**: one card's note for one skill
| Field | Type | Plain meaning |
|---|---|---|
| `card_id`, `skill` | `str` | Which card and skill (not blank) |
| `box` | `int` | Which box (≥ 1; the rule decides how many boxes there are) |
| `due` | `datetime` | When the card is next due |
| `last_seen` | `datetime` | When it was last answered |
| `right`, `wrong` | `int` | How many times right / wrong so far (≥ 0) |

Saved in the SQLite file: an `answers` table (one row per answer) and a `boxes` table (one row per card and skill; a new note replaces the old one). The file's schema version is 1 (`PRAGMA user_version`).

## Tools
- **`sqlite3`** (Python's standard library): one file, safe writes (a transaction per `record`).
- **pydantic**: `AnswerRecord`, `BoxState`.
- Nothing else: no network, no Claude, no other blocks.

## Failure modes
| Situation | What it does |
|---|---|
| The file (or its folder) doesn't exist | Made, empty |
| The file isn't a SQLite database, or is damaged | **`ProgressFileError`** (a `ValueError`) naming the file, when the store is opened. Never deleted or overwritten |
| The file is some other program's SQLite database (schema version 0 but it already has tables) | **`ProgressFileError`**; it isn't taken over or changed |
| The file was made by a newer version (schema version > 1) | **`ProgressFileError`** saying so; nothing changed |
| `box` is for another card or skill than `answer` | **`ValueError`** before anything is saved |
| A time without a timezone, a blank `card_id` / `skill` / `mode`, `box` < 1, negative counts, an unknown `decided_by` | pydantic **`ValidationError`** when the model is made |
| Anything fails (or Ctrl-C) halfway through `record` | Nothing is saved: the answer and the box note go in together or not at all. The error is passed on (a SQLite error as `ProgressFileError`) |
| Another program has the file locked for more than 5 s | **`ProgressFileError`** saying the file is busy; nothing saved |
| A saved row that breaks the models (e.g. edited by hand: `box` 0, an unknown `decided_by`) | **`ProgressFileError`** naming the file, when it's read |
| Two quizzes open a brand-new file at the same moment | One sets it up, the other waits (a locked transaction) and finds it ready |
| `box(...)` for a card never seen / `boxes(...)` for a skill with no notes | `None` / `{}` |

## How to test
Automatic tests in `tests/blocks/test_progress_store.py`, on a real SQLite file in `tmp_path`, with toy (capitals) cards only:
- **Round trip:** an answer and its box note read back exactly (incl. times, as UTC); a new note for the same card and skill replaces the old one; notes for two skills stay apart
- **`box=None`** saves the answer and leaves the old note (or none) as it was
- **Reopening** the same file (a new `ProgressStore`) finds everything; a missing folder is made
- **`answers`:** oldest first; `since` and `skill` filter; empty store → `[]`
- **All or nothing:** a failure while saving (e.g. the box write made to fail) leaves neither the answer nor the note
- **Errors:** a text file posing as the database, a newer schema version, a mismatched box, every model check above
- **Generic:** no Chinese in the block's code
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC
