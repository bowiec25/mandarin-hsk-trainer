# Block: `grader`

> **In plain words:** Mark a typed answer right or wrong against a card's answers, forgiving case, spacing and small typos.

## Goal
Mark a typed answer right or wrong against a card's answers, forgiving case, spacing and small typos.

It exists so every quiz marks answers the same fair way: it forgives slips ("Love", "loev") but not wrong words ("hate"). It is generic: it never knows about Chinese. Each quiz hands it a list of answers that are already typeable (for HSK: the answer list in `data/generated/answers.jsonl`, ADR 0006).

**Not in scope:** synonyms that aren't in the accepted answers. That needs language judgment, so it is the judge's job (ADR 0005, M4 Step 4b), asked only after the grader says wrong.

## Kind
**script.** Code can check the output: an answer either matches a listed answer (after normalising and typo tolerance) or it doesn't. It is free and instant, so it can run on every quiz turn. Judging true synonyms needs language skill, so that is left to the judge (an agent, ADR 0005), as ADR 0002 says.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `answer` | `str` | What the learner typed, e.g. `"Loev"` |
| `accepted` | `list[str]` | The card's answers, as a learner would type them, e.g. `["father", "dad", "papa"]` (from `Question.accepted_answers`) |
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
grade(answer, accepted, settings=None) -> Grade  # None = GradeSettings()
```
`GradeSettings` fields (pydantic, frozen):
- `allow_typos: bool = True` (False = exact matches only)
- `one_typo_from: int = 4` (answers this long or longer allow 1 typo; must be ≥ 1)
- `two_typos_from: int = 8` (answers this long or longer allow 2 typos; must be > `one_typo_from`)
- `ignore_leading: tuple[str, ...] = ("to", "a", "an", "the")` (a tuple, so frozen settings truly can't change)

Length is counted on the **clean accepted answer** (after normalising), not on what was typed: all its characters, spaces between words included ("ice cream" = 9).

**"Clean" text** means fully normalised: NFKC, casefolded, apostrophes (`' ’ ‘ ʼ` and backtick) and dots inside abbreviations deleted (`"one's"` → `"ones"`, `"p.m."` → `"pm"`), other punctuation turned into spaces, spaces collapsed, one leading ignored word removed **only when more words follow**. `"Love!"` and `"to love"` both become `"love"`, but a lone `"to"` stays `"to"` (real case: 给 has the meaning "to"). An accepted answer that is empty once clean (e.g. `"!!!"`) is dropped.

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
| `accepted` is empty, or every answer is empty once clean (e.g. `["!!!"]`) | **Raises `ValueError`**: a card nobody can answer is a data bug, so it must be loud |
| Exact match for one answer and a typo of another | **Exact match wins** (`typo=False`) |
| Same letters, different spacing or hyphens (`"email"` vs `"e-mail"`, `"icecream"` vs `"ice cream"`) | Counts as an **exact** match (spaces are ignored for the exact check), not a typo |
| Several answers clean to the same text | Listed **once** in `expected` |
| Odd characters (Chinese typed, "café", full-width letters) | Normalised (Unicode NFKC) and compared, no crash |
| Settings out of range (e.g. -1 typos) | pydantic **rejects** them when created |

## How to test
Automatic tests in `tests/blocks/test_grader.py` (English and toy data only, to prove the grader is generic; the one exception is Chinese *typed* as an odd input, from Failure modes):
- **Pass:** `"love"`, `"Love!"`, `"to love"`, `" love "`, `"loev"` (typo) for `["to love"]`
- **Fail:** `"hate"`, `""`, `"!!!"`; `"to"` for `["to love"]`; short words stay strict (`"eat"` for `["cat"]`)
- **Typo limits by length:** 0 / 1 / 2, including one over each limit
- **Unusable answers:** empty `accepted`, or all answers empty once clean → `ValueError`
- **Exact match beats typo match**; `expected` has no duplicates
- **Custom settings** (e.g. 0 typos) are respected; invalid settings are rejected
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

Manual check: none here; the real feel is checked in the M3 Step 6 play-test.
