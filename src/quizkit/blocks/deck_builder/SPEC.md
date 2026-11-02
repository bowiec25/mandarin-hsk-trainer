# Block: `deck_builder`

> **In plain words:** Pick which cards to quiz (by level, how many, shuffled) and turn each into a Question for a mode.

## Goal
Pick which cards to quiz (by level, how many, shuffled) and turn each into a Question for a mode.

It is the quiz's "dealer". It is its own block because "which cards next?" gets clever later: in M5 it will prefer cards you often get wrong and hold back ones seen recently (see `docs/FUTURE.md`). Then only this block changes, not the engine. Generic: no Chinese inside.

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

**How it's called** (importable from `quizkit.blocks.deck_builder`):
```python
build_deck(cards, mode, n, levels=None, seed=None) -> list[Question]
```

## Outputs
`list[Question]`, in memory (nothing saved):
- Shuffled, **no card twice**, only cards at `levels`.
- `min(n, available)` questions. Asking for more than exist gives all of them; the caller can tell by the length (e.g. the CLI says "only 197 band-2 words").
- Each made with the existing `quizkit.modes.build_question(card, mode)`, so `accepted_answers` are the card's raw answers (the engine cleans them when grading).
- The input `cards` list is not changed.

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

## How to test
Automatic tests in `tests/blocks/test_deck_builder.py` (toy data only, e.g. capitals, to prove it is generic):
- Only the chosen levels; `None` = all; several levels together
- Count: exactly `n`; `n` bigger than available gives all; no duplicates
- Same seed → same deck; different seeds → (almost always) a different order
- Questions show only the mode's fields; `accepted_answers` = the card's answers
- Input list unchanged
- Each failure mode above

Real-data check in `tests/test_hsk_deck.py`: band 1, mode `char`, n = 10 → 10 band-1 questions showing only `hanzi`; band 2 with n = 500 → all band-2 cards (the exact count is pinned in `tests/test_word_counts.py`).
