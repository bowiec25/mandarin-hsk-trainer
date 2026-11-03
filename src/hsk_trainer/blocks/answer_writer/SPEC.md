# Block: `answer_writer`

> **In plain words:** Write, for each card, the English answers a learner might type, saved to data/generated/answers.jsonl

## Goal
Write, for each card, the English answers a learner might type for that word, synonyms included (爸爸 → father, dad, papa). It runs once, offline, before you study. The quiz then accepts exactly these answers: this file is its one answer list (ADR 0006).

## Kind
**agent.** Knowing that "papa" is fine for 爸爸 but "uncle" isn't needs language judgment, which code can't do. A script (`validate_answers`) still checks the *shape* of every result: all cards present, each with 1–10 short, typeable English answers, no duplicates (ADR 0002).

## Inputs
- `cards` (`list[Card]`): the cards from `data/processed/cards.jsonl`. For each card Claude sees the hanzi, pinyin, band and the dictionary meanings, which help it pick the HSK sense (吧 = the particle, not "bar").
- `limit` (`int | None`): only do the first N cards that still need answers. The trial run is `--limit 20`. `0` asks Claude about no cards (the saved file is still tidied and written back if needed).
- `dry_run` (`bool`): print what would be sent to Claude, without calling it.
- `chunk_size` (`int`, default 40): cards per Claude call, so 978 words take about 25 calls, not 978.
- `ask` (function): what calls Claude. Default: the shared `quizkit.claude` helper (runs `claude -p`). Tests pass a fake, so they never call Claude.

**How it's called** (importable from `hsk_trainer.blocks.answer_writer`):
```python
write_answers(cards, limit=None, dry_run=False, chunk_size=40, ask=ask_claude,
              out=ANSWERS_FILE, log=LOG_FILE) -> AnswerRun
validate_answers(lines: list[AnswerLine], cards: list[Card], require_all=False) -> list[str]
load_answers(path: Path, cards: list[Card]) -> dict[str, list[str]]   # for the quiz
```
- **`load_answers`** is how the quiz reads the file (ADR 0006: it is the quiz's one answer list). It returns each card's answers by id, **only if the file is good for these cards**: every card has exactly one line, and every line for them passes the checker (after repeated answers are tidied away, as the writer does). Lines for other ids are ignored (a quiz may use only some cards). Otherwise it raises `AnswerFileError` naming the problems (the first few, plus how many more), or the line that can't be read. The writer and the quiz use the same checker, so they always agree on what a good file is.
- `ask(prompt: str) -> ClaudeReply` (from `quizkit.claude`: `text`, `model`, `input_tokens`, `output_tokens`, `cost_usd`); it raises `ClaudeError` when Claude can't be used.
- Claude is asked to reply with JSON only: `{"cards": [{"id": "...", "answers": ["...", ...]}, ...]}`.
- `AnswerLine` = one line of `answers.jsonl` (`id`, `hanzi`, `answers`, `model`, `prompt_version`).
- `AnswerRun` = the summary: `written`, `skipped` (= already in `answers.jsonl` with a current, good line; an old line kept only until it is redone is not counted), `failed` (ids of cards not saved this run, for any reason incl. the checker), `input_tokens`, `output_tokens`.
- `PROMPT_VERSION` is a string (`"1"`).
- **`ClaudeError`:** `write_answers` saves what's done, then lets the error go up; the command line prints its message. (If `claude` is missing, that happens on the first call, before anything is saved.)
- A reply wrapped in a ```` ```json ```` code fence is fine (the fence is removed).
- **Checker rules** (`validate_answers`): each id is a real card and appears once; 1–10 answers; each answer 1–40 characters of letters, digits, spaces, `'`, `.` and `-` only, with at least one letter or digit (so no Chinese, no brackets; "8" for 八 and "p.m." are fine); no duplicates in a card (compared the way the grader compares: case, punctuation and a leading to / a / an / the ignored). With `require_all=True`, every card must be present (used on the finished file).

**How you run it:** `uv run python -m hsk_trainer.blocks.answer_writer --limit 20` (add `--dry-run` to only look).

**Picks up where it left off:** cards with a current, good line in `answers.jsonl` are skipped, so a stopped run doesn't redo work.

**Never shrinks the file:** the quiz needs a line for every card, so a saved line is only removed when its card is gone from `cards.jsonl`. A line that must be redone (older `PROMPT_VERSION`, fails the checker, listed twice) **stays in the file until a new line replaces it**; if it is listed twice, one copy stays: the first that passes the checker, else the first. So a run cut short by `--limit`, a failed chunk or a `ClaudeError` never leaves the quiz with missing words.

## Outputs
1. **`data/generated/answers.jsonl`** (committed): one line per card,
   `{"id": "...", "hanzi": "爸爸", "answers": ["father", "dad", "papa"], "model": "...", "prompt_version": "1"}`.
   Saved after **every chunk** (so a stopped run keeps its work), in `cards.jsonl` order (readable git diffs).
2. **`data/generated/answer_writer_log.jsonl`** (committed, **appended** across runs): one line per Claude call: `time`, `model`, `prompt_version`, `cards`, `input_tokens`, `output_tokens`, `cost_usd` (list-price equivalent).
3. **A summary on screen** at the end, e.g. "20 written, 0 skipped, 0 failed · 4,100 tokens".

**The checker:** `validate_answers(lines, cards) -> list[str]` returns the problems found (empty = good). A card that fails is **not saved**: it is reported, and the next run tries it again.

**The reader:** `load_answers(path, cards) -> dict[str, list[str]]` gives the quiz each card's answers, after the same checker has passed the file (see Inputs).

## Tools
- **`quizkit.claude.ask_claude(prompt, model)`** (new, shared, generic): runs `claude -p --output-format json` and returns Claude's text plus token counts. **No tools switched on**, so Claude can only answer, never touch files. The judge reuses it in M4 Step 4.
- **Model:** `sonnet` (good at language judgment; runs under the subscription). Logged on every line.
- **The prompt:** saved as text in the block with a `PROMPT_VERSION`. Changing the prompt bumps the number; each answer line records which prompt made it.
- **pydantic** parses Claude's reply; a reply that isn't the JSON we asked for = that chunk failed.
- **Existing helpers:** `quizkit.files.load_cards` and `write_atomically` (no half-written files).

## Failure modes
| Situation | What it does |
|---|---|
| `claude` not installed or not logged in | Stops at once with a clear message ("run `claude` and log in"), before any work |
| A call times out or Claude errors (e.g. usage limit) | That chunk fails, nothing saved for it; the run **stops**, work so far kept; re-running continues |
| Reply isn't JSON, or the wrong shape | That chunk fails and is reported; the run goes on to the next chunk |
| Reply misses a card or adds an extra one | Missing = failed (retried next run); extra = ignored |
| One card fails the checker (0 answers, Chinese, too long…) | Only that card is skipped; the rest of the chunk is saved |
| Claude repeats an answer (as the grader sees it: "love" / "To love") | The repeat is removed before checking (it does no harm) |
| A saved line fails the checker (e.g. a hand edit), is listed more than once, or has an older `PROMPT_VERSION` | That card is asked again, but the old line **stays in the file until the new one replaces it** (if listed twice, one copy stays: the first that passes the checker, else the first). Repeated answers in saved lines are tidied and written back |
| A run stops early (`--limit`, a failed chunk, a `ClaudeError`) after a `PROMPT_VERSION` bump | The file still has a line for every card: new lines for the cards done, old lines for the rest |
| `answers.jsonl` has a card no longer in `cards.jsonl` | Dropped, with a warning printed on screen (naming the id) |
| `answers.jsonl` has a line that can't be read (e.g. a bad hand edit) | Stops before any call with `AnswerFileError` naming the line; nothing changed |
| `--dry-run` | Never calls Claude, never writes a file |
| **`load_answers`:** the file is missing, can't be opened, or isn't UTF-8 text | Raises `AnswerFileError` saying so (not a raw `OSError` or `UnicodeDecodeError`) |
| **`load_answers`:** a line can't be read | Raises `AnswerFileError` naming the line number |
| **`load_answers`:** a card has no line, a line is listed twice, or a line fails the checker | Raises `AnswerFileError` listing the problems (first 5, then "and N more") |
| **`load_answers`:** lines for ids not in `cards` | Ignored |
| **`load_answers`:** blank lines | Skipped (as the writer does) |
| **`load_answers`:** a line repeats an answer ("love" / "To love") | Tidied away, like the writer does (they do no harm), so the two never disagree; then the checker runs |

## How to test
**Automatic** (`tests/blocks/test_answer_writer.py`), with a **fake Claude** (free, fast, offline):
- **Checker:** good answers pass; each kind of bad one is caught (empty, Chinese, too long, duplicates, missing card).
- **Resume:** a second run skips cards already done.
- **Saving:** a failed card isn't saved; the good ones in its chunk are.
- **Problems:** a broken reply or Claude down handled as in the table above.
- **`--dry-run`:** no calls, no file. **`--limit 20`:** exactly 20 written.
- **Never shrinks:** after a `PROMPT_VERSION` bump, a run stopped by `--limit`, a failed chunk or a `ClaudeError` still leaves a line for every card.
- **`load_answers`:** a good file gives every card's answers; each problem in the table raises `AnswerFileError`; lines for other ids are ignored.
- **Real file:** `load_answers` reads the committed `answers.jsonl` for the real 978 cards with no problems.

**By hand:**
1. **Trial:** `--limit 20`, you read the 20 → if good, the full run.
2. **After the full run:** you spot-check 20 random words.
