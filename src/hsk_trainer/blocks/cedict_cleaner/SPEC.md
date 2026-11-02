# Block: `cedict_cleaner`

> **In plain words:** Turn one CC-CEDICT dictionary meaning into zero or more answers a learner could type.

## Goal
Turn one CC-CEDICT dictionary meaning into zero or more answers a learner could type.

The dictionary's meanings are written for readers, not for typing: they carry notes like "(coll.)", "sb/sth", "surname Bai" and "abbr. for 超级市场". This block is the HSK **cleaner** passed to the generic `grader` (`quizkit.blocks.grader`), so the grader stays free of Chinese. It does not change `cards.jsonl`: the original wording stays there, so it can still be shown as feedback.

## Kind
**script.** The rules are fixed text patterns (remove "(coll.)", drop "surname X"), so code applies them, and code can check the result: every one of the 978 real cards must keep at least one typeable answer. No language judgment is needed, so no agent (ADR 0002).

## Inputs
One dictionary meaning (`str`), e.g. `"(coll.) father"`: one item of a `Card.answers` list.

**How it's called** (importable from `hsk_trainer.blocks.cedict_cleaner`):
```python
clean_answer(meaning: str) -> list[str]
```
This is the `cleaner` shape the grader expects: `grade(answer, card.answers, cleaner=clean_answer)`.

**Rules** (built from the patterns in the 978 real cards). Rules 1, 2, 4 run first. Then, if rule 5 or 6 gives items, those items **replace** the meaning and rules 3 and 7 don't apply; otherwise rules 3 and 7 add their extras. Rule 8 checks every result:

| # | Rule | Example in → out |
|---|---|---|
| 1 | **Drop** meanings that aren't the HSK meaning: starting `surname`, `abbr.`, `also written`, `also pr.`, `Taiwan pr.`; containing `variant of`; `see` / `used in` followed by Chinese. Checked on the raw meaning **and** again after notes are removed (so `"(Tw) surname Bai"` is dropped too) | `"surname Bai"` → `[]` |
| 2 | **Remove** `(…)` notes and `[…]` pinyin | `"(coll.) father"` → `["father"]` |
| 3 | If a removed note is **one plain word** (letters only, not a label like `(coll.)`, `(Tw)`, `(slang)`, `(sb)`), **also** keep a version with it | `"(cooked) rice"` → `["rice", "cooked rice"]` |
| 4 | **Remove** placeholder words `sb`, `sth` (also `sb's`, `sth's`), `etc` and `...` / `…` | `"to let sb off lightly"` → `["to let off lightly"]` |
| 5 | **Colon lists** replace the meaning: the items after `:`, split on commas | `"…: some, a few, several"` → `["some", "a few", "several"]` |
| 6 | **Classifiers** (no colon) replace the meaning: the items after `classifier for`, split on commas | `"classifier for vehicles"` → `["vehicles"]` |
| 7 | **Commas** (other meanings): keep the whole meaning **and** the part before the first comma | `"date, day of the month"` → `["date, day of the month", "date"]` |
| 8 | **Drop** any result that still contains Chinese characters or is empty; no duplicates | `"the Great Learning, one of the Four Books 四书"` → `["the Great Learning"]` |

Case, a leading "to", punctuation and typos are the grader's job, not this block's.

## Outputs
`list[str]`: zero or more clean answers, returned in memory. Nothing is saved to a file.
- `[]` means "not a typeable answer" (e.g. a surname); the grader drops it.
- Results have no `(…)`, `[…]` or Chinese characters, and no duplicates. Each is trimmed, with spaces collapsed after removals (`"...right?"` → `"right?"`).
- Order: the main cleaned version first, then the extras from rule 3 (note kept) and rule 7 (part before the comma), as in the Inputs table.
- "Passed through unchanged" means exactly unchanged (case and punctuation kept).
- Always a list, never a bare string (the grader would reject that with `TypeError`).

## Tools
- **Python built-ins only**: `re` for the patterns; Chinese characters detected by Unicode range (U+3400–U+9FFF common hanzi + extension A, U+F900–U+FAFF compatibility ideographs, U+20000 and up for extensions B+).
- No new libraries, no files, no network, no agent.
- Tests only: `data/processed/cards.jsonl` (read-only) for the "all 978 cards" check.

## Failure modes
| Situation | What it does |
|---|---|
| Meaning that is only clutter (`"(modal particle …)"`, `"surname Bai"`) | Returns `[]`, no crash |
| Empty or blank string | Returns `[]` |
| Unbalanced brackets, e.g. `"(coll. father"` | No crash: leftover brackets are removed, the words stay |
| A pattern no rule knows | Passed through unchanged (the grader still handles case and punctuation) |
| A card where **every** meaning becomes `[]` | Not this block's error (it sees one meaning at a time): the grader raises `ValueError`, and the 978-card test (How to test) catches it before any quiz runs |

## How to test
Automatic tests in `tests/blocks/test_cedict_cleaner.py`:

**Unit tests**
- One test per rule (1–8), using the examples in the Inputs table
- Each failure mode: blank, only clutter, unbalanced brackets, unknown pattern
- Outputs: always a list; no `(`, `[` or Chinese characters; no duplicates

**Real-data tests** (all 978 cards in `data/processed/cards.jsonl`)
- Every card keeps **at least one** typeable answer through `clean_answer` (this covers 些 and 辆)
- With the grader: for every card, typing its first clean answer is marked correct by `grade(..., cleaner=clean_answer)`
- Spot checks: 爸爸 accepts "father" and "dad"; 米饭 accepts "rice"; 辆 accepts "vehicles"; 百 does **not** accept "Bai"

Manual check: none here; the M3 Step 6 play-test checks the feel.
