# Block: `grader`

> **In plain words:** Mark a typed answer right or wrong against a card's answers, forgiving case, spacing and small typos.

## Goal
Mark a typed answer right or wrong against a card's answers, forgiving case, spacing and small typos.

It exists so every quiz marks answers the same fair way: it forgives slips ("Love", "loev") but not wrong words ("hate"). It is generic: a quiz can pass in its own **cleaner** (e.g. the HSK one that strips dictionary notes like "(coll.)"), so the grader itself never knows about Chinese.

**Not in scope (yet):** synonyms that aren't in the card's answers ("papa" for 爸爸 when only "father" / "dad" are listed). That needs language judgment, so it is the optional agent fallback planned for M5.

## Kind
**script.** Code can check the output: an answer either matches a listed answer (after cleaning and typo tolerance) or it doesn't. It is free and instant, so it can run on every quiz turn. Judging true synonyms needs language skill, so that is left to a later, optional agent fallback (M5), as ADR 0002 says.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `answer` | `str` | What the learner typed, e.g. `"Loev"` |
| `accepted` | `list[str]` | The card's answers, e.g. `["to love", "(coll.) father"]` (from `Question.accepted_answers`) |
| `cleaner` | `Callable[[str], list[str]] \| None` | Optional. Turns one messy answer into **zero or more** clean versions: `"(cooked) rice"` → `["cooked rice", "rice"]`, `"surname Bai"` → `[]` (dropped). `None` = use each answer as it is |
| `settings` | `GradeSettings` (pydantic) | How forgiving to be. Defaults below |

**Default `GradeSettings`:**
- Ignore case, extra spaces and punctuation (`"Love!"` = `"love"`)
- `ignore_leading`: a leading `to` / `a` / `an` / `the` is ignored (`"love"` = `"to love"`)
- Typos allowed by word length (short words stay strict):
  - 1–3 letters: **0** (`"cat"` ≠ `"eat"`)
  - 4–7 letters: **1** (`"loev"` ✓)
  - 8+ letters: **2**

Typo limits and ignored words are settings, so another quiz can change them.

**How it's called** (all importable from `quizkit.blocks.grader`):
```python
grade(answer, accepted, cleaner=None, settings=GradeSettings()) -> Grade
```
`GradeSettings` fields (pydantic, frozen):
- `allow_typos: bool = True` (False = exact matches only)
- `one_typo_from: int = 4` (answers this long or longer allow 1 typo; must be ≥ 1)
- `two_typos_from: int = 8` (answers this long or longer allow 2 typos; must be > `one_typo_from`)
- `ignore_leading: tuple[str, ...] = ("to", "a", "an", "the")` (a tuple, so frozen settings truly can't change)

Length is counted on the **clean accepted answer** (after normalising), not on what was typed: all its characters, spaces between words included ("ice cream" = 9).

**"Clean" text** means fully normalised: NFKC, casefolded, punctuation removed, spaces collapsed, one leading ignored word removed **only when more words follow**. `"Love!"` and `"to love"` both become `"love"`, but a lone `"to"` stays `"to"` (real case: 给 has the meaning "to"). An accepted answer that is empty once clean (e.g. `"!!!"`) is dropped, just like one the cleaner drops.

## Outputs
One `Grade` (pydantic, frozen), returned in memory. Nothing is saved to a file. `matched` and `expected` hold **clean** text (see Inputs); `expected` keeps first-seen order.

| Field | Type | Plain meaning |
|---|---|---|
| `correct` | `bool` | Right or wrong |
| `matched` | `str \| None` | The clean answer it matched, e.g. `"love"`; `None` if wrong |
| `typo` | `bool` | `True` if it only counted thanks to typo forgiveness (so the quiz can say "check spelling: *love*") |
| `expected` | `list[str]` | All clean answers, for feedback ("the answer was: love, like…") |

## Tools
- **`rapidfuzz`**: `rapidfuzz.distance.OSA` counts typos, with a swap of two neighbouring letters as **one** typo ("loev" → "love" = 1). Plain Levenshtein would count it as 2.
- **Python built-ins**: `str.casefold`, `unicodedata`, `re` for case, space and punctuation clean-up.
- **pydantic**: `GradeSettings`, `Grade`.
- No files, no network, no agent.

## Failure modes
| Situation | What it does |
|---|---|
| Blank answer, or only punctuation | Marks it **wrong** (`correct=False`), no crash |
| A lone ignored word typed ("to") | A normal answer: wrong unless "to" is accepted (or within typo reach, e.g. "the" for "then") |
| `accepted` is empty, or the cleaner drops *every* answer | **Raises `ValueError`**: a card nobody can answer is a data bug, so it must be loud |
| The cleaner raises | The error is passed through (a cleaner bug must not be hidden) |
| The cleaner returns a plain string instead of a list (`"rice"` not `["rice"]`) | **Raises `TypeError`** (otherwise it would silently split into letters) |
| Exact match for one answer and a typo of another | **Exact match wins** (`typo=False`) |
| Several answers clean to the same text | Listed **once** in `expected` |
| Odd characters (Chinese typed, "café", full-width letters) | Normalised (Unicode NFKC) and compared, no crash |
| Settings out of range (e.g. -1 typos) | pydantic **rejects** them when created |

## How to test
Automatic tests in `tests/blocks/test_grader.py` (English and toy data only, to prove the grader is generic; the one exception is Chinese *typed* as an odd input, from Failure modes):
- **Pass:** `"love"`, `"Love!"`, `"to love"`, `" love "`, `"loev"` (typo) for `["to love"]`
- **Fail:** `"hate"`, `""`, `"!!!"`; `"to"` for `["to love"]`; short words stay strict (`"eat"` for `["cat"]`)
- **Typo limits by length:** 0 / 1 / 2, including one over each limit
- **Cleaner:** one answer → several; one → `[]` (dropped); all dropped → `ValueError`
- **Exact match beats typo match**; `expected` has no duplicates
- **Custom settings** (e.g. 0 typos) are respected; invalid settings are rejected
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

Manual check: none here; the real feel is checked in the M3 Step 6 play-test.
