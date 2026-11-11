# Block: `live_sentences`

> **In plain words:** During the quiz, get each sentence-mode question its sentence: ask Claude ahead in the background when the bank's rule says new, bank what passes, and fall back to the bank when Claude is slow or failing.

## Goal
During the quiz, get each sentence-mode question its sentence: ask Claude ahead in the background when the bank's rule says new, bank what passes, and fall back to the bank when Claude is slow or failing.

It exists for ADR 0011: new sentences while you play, a bank that grows by itself, and a quiz that never gets stuck. Measured 2026-11-04: one word, one `claude -p` call with Sonnet takes about 4 s and about 2,900 tokens, so asking while you answer the previous word usually hides the wait.

**Not in scope:** writing and checking a sentence (`sentence_writer.write_one`); the rule and the file (`sentence_bank`); printing (the CLI).

## Kind
**script.** It decides when to ask, how long to wait and what to show: plain scheduling and fallbacks that code can check. The language work happens in `sentence_writer.write_one`, whose output its checks have already passed (ADR 0002).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `bank` | `SentenceBank` | The bank: its rule (`wants_new`), its sentences (`banked`), `add`, `mark_seen`, and its removed list (`is_removed`, ADR 0015) |
| `cards` | `list[Card]` | All the cards (to find the card for an id) |
| `write` | function `Card -> WrittenSentences` | Writes and checks new sentences for one word. Default: `sentence_writer.write_one` with these cards. Tests pass a fake |
| `wait` | `float` (default 15) | Seconds to wait for a sentence that's still being written, once its question is up |
| `max_failures` | `int` (default 2) | Failures in a row before live sentences switch off for this quiz |
| `enabled` | `bool` (default True) | False = bank only (`--no-live`) |
| `before_waiting` | function or None | Called once when a question has to wait (the CLI prints "writing a sentence…") |

**How it's called** (importable from `hsk_trainer.blocks.live_sentences`):
```python
live = LiveSentences(bank, cards, write=None, wait=15.0, max_failures=2,
                     enabled=True, before_waiting=None)
live.prepare(card_id)               # draw new-or-banked now; if new, start writing
live.sentence_for(card_id) -> Shown # the sentence to show (prepares first if needed)
live.finish(seconds=5.0) -> list[str]  # end of quiz: bank what's still being written
```

## Outputs
**`Shown`** (pydantic, frozen): `sentence: Sentence | None`, `source: "new" | "banked" | "none"`, `note: str | None` (one line for the screen, e.g. "live sentences switched off for this quiz: …", "couldn't save which sentences you've seen: …").

What `sentence_for` does:
1. **Background job ready** (or ready within `wait`) with at least one sentence: every sentence is offered to `bank.add` (the bank refuses repeats, removed sentences and a full word), the first one **not on the bank's removed list** (`bank.is_removed`, ADR 0015) is shown, `source="new"`, and failures go back to 0.
2. **Job failed, gave no sentence that passed, gave only removed sentences, or isn't ready within `wait`:** counts as one failure. At `max_failures` in a row, live sentences switch off (`note` says why). Then it falls back to the bank.
3. **Bank fallback / rule said banked / live off:** `bank.banked(card_id)`, giving `source="banked"`, or `None` and `source="none"`.
4. The shown sentence is passed to `bank.mark_seen`.

**Late results:** a job that finishes after its question has moved on isn't wasted. Its sentences are banked at the next `sentence_for` or `prepare` call (a note from that, e.g. a failed save, comes with the next `Shown`). A late success does **not** reset the failure count: only a sentence actually shown does. All **bank** file writes (`add`, `mark_seen`) happen on the quiz's own thread; background threads only call `write` (the real one, `write_one`, appends its own log line, under a lock). A late job that failed or gave nothing is simply dropped.

**Small rules:**
- A job that's already finished when its question comes up is used at once: no `before_waiting`, no wait.
- After live switches off, a job that's already finished is still used; one that isn't is never waited for (it's banked later if it finishes) and doesn't count as a failure.
- A new sentence that's already in the bank still counts as `source="new"` (Claude wrote it this time); the bank just doesn't store it twice.
- A new sentence an audit removed earlier (on the bank's removed list) is **never shown**, even though it passed the scripts: Claude may write the same sentence again. If it was the job's only one, that's one failure and the bank is used. If a later sentence of the job is shown instead, that's a success (failures go back to 0). The list is asked at the moment (each `is_removed` / `add` call), so a sentence removed mid-quiz isn't shown or banked afterwards. A late job that gave only removed sentences is dropped, like any late job that gave nothing: not a failure.
- Waiting happens in short slices, so Ctrl-C stops the quiz at once.
- More than one note in one question are joined with "; ".

**End of the quiz:** `finish` waits up to 5 s for sentences still being written (the last question's, or a late one) and banks them, so a paid call isn't lost; it returns any notes. Ctrl-C skips the wait.

**Background threads** are daemon threads: quitting never waits longer than `finish` allows. A `claude` call still running then finishes on its own (at most `write_one`'s 30 s limit), unlogged.

**The default `write`** is `write_one` with the checker's word list built once, on the first call: a problem building it counts as one failure, so a bad line in another band never stops a quiz.

## Tools
- `hsk_trainer.blocks.sentence_bank.SentenceBank`, `hsk_trainer.blocks.sentence_writer` (`write_one`, `WrittenSentences`, `Sentence`).
- `threading` (a daemon thread per job, an `Event` to wait on), pydantic.

## Failure modes
| Situation | What it does |
|---|---|
| `write` raises (`ClaudeError`: missing, not logged in, timeout, usage limit; or anything else) | One failure; bank fallback |
| `write` returns no sentences (none passed the checks) | One failure; bank fallback |
| `write` returns only sentences on the removed list | One failure; bank fallback; none banked or shown |
| Not ready within `wait` | One failure; bank fallback; its sentences are banked later if it finishes |
| `max_failures` in a row | Live off for the rest of the quiz, with a `note`; no more jobs started |
| `bank.mark_seen` raises `OSError` (file locked) | Shown anyway; a `note` the first time only |
| `bank.add` raises `OSError` (file locked) | Shown anyway; a `note` (naming the word) the first time only |
| `card_id` not one of the cards | `ValueError` |
| `enabled=False` | Never calls `write`; always the bank |
| `prepare` twice for one id | The second does nothing |

## How to test
- `tests/blocks/test_live_sentences.py`, with a toy bank in `tmp_path` and a **fake `write`** (never Claude), which can be instant, failing, slow (an `Event` the test releases) or empty:
  - rule says new and the job is ready, so it's shown and banked;
  - rule says banked, so `write` is never called;
  - waiting: `before_waiting` is called once and the job finishes in time;
  - not ready within a short `wait`, so the bank is used, and the late result is banked at the next call;
  - `write` raises or returns nothing, so the bank is used and it counts as a failure;
  - `write` returns a removed sentence first: the next one is shown instead; only removed ones: the bank is used, one failure, nothing banked;
  - 2 failures in a row switch it off, with a note, and no more jobs start;
  - a success resets the count;
  - `enabled=False`;
  - `mark_seen` is called, and an `OSError` from it gives a note once;
  - an unknown id raises; `prepare` twice; threads are daemons.
- `sentence_writer.write_one`: one call; passing sentences returned with laid-out pinyin; failing ones dropped; a broken reply gives `[]`; a `ClaudeError` goes up; one log line (`cards` 1, `retry` 0).
- **CLI:** `--no-live` never calls Claude; a live sentence is shown and banked (with a fake writer); the next question's sentence is prepared while you answer.
