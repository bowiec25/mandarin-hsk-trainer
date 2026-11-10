# Block: `deck_builder`

> **In plain words:** Pick which cards to quiz (by level, how many, shuffled) and turn each into a Question for a mode.
> With a schedule (M5, ADR 0013), it deals the words that are **due** first, then new ones.

## Goal
Pick which cards to quiz (by level, how many, shuffled) and turn each into a Question for a mode.

It is the quiz's "dealer". It is its own block because "which cards next?" gets clever later: in M5 (ADR 0013) it takes an optional **schedule** (when each card is next due, from the Leitner boxes) and deals due cards first. Only this block changed, not the engine. Generic: no Chinese inside.

## Kind
**script.** Filtering, counting and shuffling can all be checked by code (right levels, right count, no repeats, same seed = same deck). No judgment needed (ADR 0002).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `cards` | `list[Card]` | All the cards to choose from (the CLI loads them; this block reads no files) |
| `mode` | `Mode` | Which fields each question shows (e.g. a capitals quiz's `country` mode shows only the country) |
| `n` | `int` | How many questions are wanted (≥ 1) |
| `levels` | `list[int] \| None` | Only cards at these levels. `None` = all levels. A list, so "bands 1+2 together" later is free; `--band 2` passes `[2]` |
| `seed` | `int \| None` | Same seed → same deck (for tests and repeatable runs). `None` = different every time |
| `schedule` | `Mapping[str, datetime] \| None` | When each card is next due, by card id, for this quiz's skill. A card not in it is **new**. `None` = no schedule: today's plain shuffle |
| `now` | `datetime \| None` | The time to compare `due` against. `None` = the current time (UTC). Only used with a schedule |

**How it's called** (importable from `quizkit.blocks.deck_builder`):
```python
build_deck(cards, mode, n, levels=None, seed=None, schedule=None, now=None) -> list[Question]
```

## Outputs
`list[Question]`, in memory (nothing saved):
- Shuffled (without a schedule; with one, see the order below), **no card twice**, only cards at `levels`.
- `min(n, available)` questions. Asking for more than exist gives all of them; the caller can tell by the length (e.g. the CLI says "only 197 band-2 words").
- Each made with the existing `quizkit.modes.build_question(card, mode)`, so `accepted_answers` are the card's answers as they are (the grader normalises case, spaces and punctuation when it compares).
- The input `cards` list is not changed.

**With a schedule**, the deck is dealt in this order (ADR 0013), and the questions keep that order:
1. **due** cards (`due <= now`), most overdue first;
2. **new** cards (not in the schedule), shuffled;
3. only if `n` isn't filled yet: cards **not due yet**, soonest first.

Cards with the same due time are in a shuffled order (same seed → same order). Schedule entries for cards not in the pool (other levels, unknown ids) are ignored, not even checked, so one bad entry elsewhere can't stop this deck. A schedule that knows none of the pool's cards (`{}`, or a first quiz) means every card is new: **the same deck as `schedule=None`** for the same seed (given a valid `now`), so a replay with `--seed` matches. "Most overdue" = earliest due time, compared as real moments across timezones; `now` is read once per call.

## Tools
- Python `random.Random(seed)` (its own random generator, so a seed doesn't affect anything else).
- `quizkit.modes.build_question`, `quizkit.models.Card` / `Question`, `quizkit.modes.Mode`.
- No files, no network, no agent.

## Failure modes
| Situation | What it does |
|---|---|
| `n` not a whole number (`2.0`, `True`) | Raises `TypeError` |
| `n < 1` | Raises `ValueError` |
| The same card id appears twice in `cards` | Counted once (first copy wins), so no card comes up twice |
| `cards` is empty | Raises `ValueError` ("no cards to build a deck from") |
| No card is at the chosen `levels` | Raises `ValueError` naming the levels (a quiz of 0 questions is a mistake, so say so) |
| `levels` is an empty list | Raises `ValueError` (use `None` for "all") |
| A card at the chosen levels lacks a field the mode shows | `build_question`'s `MissingFieldError` is passed through. **Every** card at the chosen levels is checked, not just the drawn ones, so it fails every time, not by luck |
| `n` larger than the cards available | Not an error: returns all of them, shuffled |
| Some chosen levels have cards, others don't (`levels=[1, 99]`) | Not an error: uses the cards it has |
| A schedule value for a card in the pool, or `now`, that isn't a `datetime` (`None`, a `date`, text) | Raises `TypeError` |
| A schedule time for a card in the pool, or `now`, has no timezone (with a schedule) | Raises `ValueError` (naive and aware times can't be compared safely) |
| `now` given without a schedule | Ignored, not even checked |

## How to test
Automatic tests in `tests/blocks/test_deck_builder.py` (toy data only, e.g. capitals, to prove it is generic):
- Only the chosen levels; `None` = all; several levels together
- Count: exactly `n`; `n` bigger than available gives all; no duplicates
- Same seed → same deck; different seeds → (almost always) a different order
- Questions show only the mode's fields; `accepted_answers` = the card's answers
- Input list unchanged
- Schedule: due first (most overdue first), then new (shuffled), then not-due (soonest first) only to fill `n`; ties shuffled by seed; extra schedule ids ignored; `{}` = the same deck as no schedule; `due == now` counts as due; no timezone → `ValueError`; not a datetime → `TypeError`
- Each failure mode above

Real-data check in `tests/test_hsk_deck.py`: band 1, mode `char`, n = 10 → 10 band-1 questions showing only `hanzi`; band 2 with n = 500 → all band-2 cards (the exact count is pinned in `tests/test_word_counts.py`).
