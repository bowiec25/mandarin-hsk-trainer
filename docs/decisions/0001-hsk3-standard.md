# 0001: Use the HSK 3.0 word lists (bands 1–3)

- **Status:** Accepted (2026-11-01). **Word counts superseded by [0004](0004-word-list-source.md)** (2026 revised syllabus: 300 / 500 / 1,000). The choice of HSK 3.0, bands 1–3, still stands.
- **In plain words:** we teach the words from the **current** HSK standard (HSK 3.0, from 2021), not the old one, and start with bands 1–3.

## Context
There are two HSK word-list standards:
- **HSK 2.0** (2010): 6 levels. Most older apps and flashcard decks use it.
- **HSK 3.0** (2021, *Chinese Proficiency Grading Standards for International Chinese Language Education*): 9 bands, larger lists, and it's the one the exam is moving to.

The two lists differ a lot, so we have to choose one.

## Decision
Use **HSK 3.0**, **bands 1–3** only for now. Cumulative word counts are roughly:

| Band | Words (cumulative) |
|---|---|
| 1 | ~500 |
| 2 | ~1,272 |
| 3 | ~2,245 |

Every card stores its `band`, so a quiz can be filtered by band.
The exact source file is chosen and pinned (URL + checksum, licence checked) in M2.

## Why / alternatives considered
- **HSK 2.0:** more existing material, but it's being replaced. Learning an outdated list wastes effort.
- **All 9 bands at once:** too big to review well. Bands 1–3 are enough to be useful, and more can be added later without redesigning anything.

## Consequences
- ✅ Matches the current exam and the user's learning goal.
- ✅ Band is just a field, so extending to bands 4–9 is a data change, not a code change.
- ⚠️ Fewer ready-made open datasets than for HSK 2.0, so the source needs care in M2 (licence, duplicates, words with several meanings).
- ⚠️ Totals may differ slightly between sources (duplicates, variants). Tests allow a known tolerance.
