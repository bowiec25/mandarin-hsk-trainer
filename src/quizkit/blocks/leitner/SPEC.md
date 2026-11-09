# Block: `leitner`

> **In plain words:** Move a card's box after an answer (right: up one, wrong: back to box 1) and say when it's next due.

## Goal
Move a card's box after an answer (right: up one, wrong: back to box 1) and say when it's next due.

It is the **teacher who moves the flashcards** (ADR 0013). `progress_store` only files the notes; this block decides what the new note says. It's one small pure function plus its settings, so the rule is easy to test and to change later (e.g. after Claude reviews how the learning is going, FUTURE.md). Generic: no Chinese, any quiz can use it.

## Kind
**script.** Every result can be checked by code (box 3 + right = box 4, due in 7 days). No judgment, no files, no network (ADR 0002).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `old` | `BoxState \| None` | The card's current note for this skill (from `progress_store`). `None` = a new card, never answered |
| `card_id`, `skill` | `str` | Which card and skill the answer was for (must match `old` if given) |
| `correct` | `bool \| None` | Right or wrong. `None` = nobody could check it: **the box doesn't move** (ADR 0013) |
| `at` | `datetime` | When it was answered (timezone-aware) |
| `rule` | `LeitnerRule` | The waits. Default: 5 boxes, waiting 0 / 1 / 3 / 7 / 21 days |

**How it's called** (importable from `quizkit.blocks.leitner`):
```python
new = next_box(
    old, card_id, skill, correct, at, rule=DEFAULT_RULE
)  # -> BoxState | None
DEFAULT_RULE.waits  # (0 days, 1 day, 3 days, 7 days, 21 days): one per box
```
The result goes straight to `progress_store.record(answer, new)`.

## Outputs
`BoxState | None` (the model from `progress_store`):
- **Right:** one box up (at most the last box). A **new** card answered right goes to **box 2**: you knew it the first time, so it waits a day instead of coming straight back (with a one-box rule: box 1, the last box).
- **Wrong:** box 1 (new or not).
- `due` = `at` + the wait for the new box; `last_seen` = `at`; `right` / `wrong` = the old counts + 1 on the right side (a new card starts from 0).
- **`correct=None`:** returns `None` (nothing to change; the store keeps the old note).

**`LeitnerRule`** (frozen pydantic): `waits: tuple[timedelta, ...]`, one wait per box, box 1 first. At least 1 box; no negative wait; each wait at least as long as the one before (equal waits are fine); none longer than 10 years. `new_right_box` (default 2, ≥ 1): where a new card answered right starts (the user's choice, 2026-11-10); capped at the last box.

## Tools
- `quizkit.blocks.progress_store.BoxState` (the note's shape), `datetime` / `timedelta`, pydantic. Nothing else: it reads and writes no files.

## Failure modes
| Situation | What it does |
|---|---|
| `old` is for another card or skill | **`ValueError`** (checked first, even when `correct` is `None`) |
| `at` has no timezone | **`ValueError`** (checked first, even when `correct` is `None`) |
| `at` is before `old.last_seen` (a clock went back) | Allowed: the result uses `at` as given (the store keeps whatever it's handed) |
| `old.box` is higher than the rule's last box (the rule was changed to fewer boxes) | Treated as the last box |
| A rule with no boxes, a negative wait, a wait over 10 years, waits that get shorter, or `new_right_box` < 1 | pydantic **`ValidationError`** when the rule is made |

## How to test
Automatic tests in `tests/blocks/test_leitner.py`, toy capitals cards only:
- **Every move:** new + right → box 2; new + wrong → box 1; box 3 + right → box 4; box 5 + right → stays 5; any box + wrong → 1; `correct=None` → `None`
- **Due times:** due = `at` + the wait for the new box, for every box (default rule) and for a custom rule
- **Counts and last_seen** update; a new card starts from 0
- **Errors:** mismatched card or skill, `at` without a timezone, bad rules; an `old.box` above the last box is treated as the last
- **Generic:** no Chinese in the block's code
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC
