# Block: `normalizer`

> **In plain words:** Turn the raw HSK word lists (data/raw/hsk3_2026/) into Card records, one per word, saved to data/processed/cards.jsonl.

## Goal
Turn the 3 raw HSK word lists (bands 1–3) into one clean, flat file of `Card` records, one card per word. Every later step (quiz, sentences) reads only this file, so none of them need to know the raw format.

## Kind
script: it only reshapes data (no language judgment), and code can check every card (counts, fields, no blanks).

## Inputs
- Called as `run(src, dest) -> list[Card]` (both optional); also runnable by hand: `uv run python -m hsk_trainer.blocks.normalizer`
- `src: Path`: the folder holding the raw lists (optional, default `data/raw/hsk3_2026/`). It reads `1.json`, `2.json`, `3.json`; the file number is the band.
- `dest: Path`: where to write the cards (optional, default `data/processed/cards.jsonl`)
- From each raw word it uses only `simplified` (the characters), `forms[].transcriptions.pinyin`, `forms[].meanings` and `pos` (part of speech). Everything else (traditional, radical, etc.) is ignored.
- Each raw file must be a JSON list of words.

## Outputs
- `list[Card]`, also written to `dest` as **one card per line** (JSON, UTF-8, Chinese kept readable). Order: band 1, then 2, then 3, each in the raw file's order (978 cards).
- Each `Card` (example: 爱):
  - `id`: the characters, `"爱"` (no word is in two bands, so it's unique; stays stable so later files, e.g. audio, can be named after it)
  - `level`: the band (1, 2 or 3)
  - `fields`: `{"hanzi": "爱", "pinyin": "ài", "pos": "v, vn, b", "readings": "1"}`
    - `pos` may be empty (`""`): 11 real words have no part of speech, and that's not an error
    - several readings → pinyin joined `"bā / ba / biā"` (repeats removed, raw order kept); `readings` = how many distinct pinyin readings
  - `answers`: every meaning of every reading, split at `;` (not at a `;` inside `()` or `[]`), trimmed, exact repeats removed (case matters), order kept, e.g. `["to love", "to be fond of", "to like", "affection", …]`
- Same input → byte-identical file (so git only shows real data changes).
- **Known gap:** for multi-reading words we don't know which reading HSK means (form order in the source isn't HSK-relevant), so all are kept. Fine for v1 (reading quiz); `readings` lets us find these words if exam listening practice is added later.

## Tools
- Python's built-in `json` and `pathlib`: no new libraries
- `quizkit.models.Card`: pydantic checks every card as it's made (no blank answers, level ≥ 1), so a broken card can't reach the file

## Failure modes
All errors are a `NormalizeError` (defined in this block) whose message names the file, and the word and `band N` where there is one. On any error nothing is written.
- A raw file is missing, isn't valid JSON, or isn't a list of words → error naming the file
- A word has no characters, no readings (`forms` empty), a reading with blank pinyin, or no non-blank meanings → error naming the word and band (bad data never slips through silently)
- The same word appears twice (in one band or across bands) → error, since ids must be unique
- Output folder missing → create it
- Never leave a half-written `cards.jsonl`: write to a temp file first, then swap it in (an old good file stays if anything fails)

## How to test
- Tests use small fake raw files in a temp folder: fast, and never touch the real data
- One test per failure mode above
- Shape tests (爱, 吧): right `id`, `level`, `fields`, `answers`; multi-reading pinyin joined with `readings` = `"3"`; split at `;` but not inside brackets
- Running twice gives a byte-identical file
- Real check, by hand: `uv run python -m hsk_trainer.blocks.normalizer` writes 978 cards (exact per-band counts become an automatic test in M2 Step 6)
