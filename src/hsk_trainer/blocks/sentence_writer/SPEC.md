# Block: `sentence_writer`

> **In plain words:** Ask Claude for 1-2 short example sentences per word, with pinyin and English; keep only the ones the scripts pass (retrying failures with the reasons), and save them to data/generated/sentences.jsonl.

## Goal
Ask Claude for 1-2 short example sentences per word, with pinyin and English; keep only the ones the scripts pass (retrying failures with the reasons), and save them to data/generated/sentences.jsonl.

It exists to unlock the quiz modes `char_sentence` and `full` (ADR 0008, ADR 0010): a word is easier to learn in a sentence. It runs **offline, as a batch**, before anyone studies; the quiz only reads the file.

**Not in scope:** reading the file for the quiz (PR 5, the wiring); judging whether a sentence is natural (the user's spot-check, then the `data-auditor` subagent in Step 6).

## Kind
**agent.** Writing a natural sentence from a small word list needs language skill (ADR 0002). As ADR 0002 requires: scripts check every sentence (`sentence_validator`, ADR 0009) and its pinyin (ADR 0010), it has `--limit` / `--dry-run`, and it logs the model, prompt version and tokens. Same shape as `answer_writer`.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `cards` | `list[Card]` | **All** the cards (`cards.jsonl`): hanzi, pinyin, band, dictionary meanings. Always the whole deck: it is also the checker's word list (a trial uses `limit`, not fewer cards) |
| `limit` | `int \| None` | Only the first N words that still need sentences (trial: `--limit 20`) |
| `dry_run` | `bool` | Show the first prompt; never call Claude, never write a file |
| `chunk_size` | `int` (default 20) | Words per Claude call (one band per call) |
| `retries` | `int` (default 2) | Extra tries for a word whose sentences all failed the checker |
| `removed` | `Path` (default `REMOVED_FILE`, `data/generated/sentences_removed.json`) | The removed-sentences list (ADR 0015): word → sentences an audit removed. Never saved again. Missing = empty |
| `ask` | function | Calls Claude. Default `quizkit.claude.ask_claude` (`claude -p`, no tools). Tests pass a fake |
| `card` | `Card` | `write_one` only: the one word to write for |
| `vocab` | `Vocab \| None` | `write_one` only: the checker's word list, built once by the caller (else built from `cards`) |
| `timeout` | `float` (default 30, near the quiz's 15 s wait) | `write_one` only: seconds before the Claude call gives up |

**How it's called** (importable from `hsk_trainer.blocks.sentence_writer`):
```python
write_sentences(cards, limit=None, dry_run=False, chunk_size=20, retries=2,
                ask=ask_claude, out=SENTENCES_FILE, log=LOG_FILE,
                removed=REMOVED_FILE) -> SentenceRun
pinyin_problems(sentence, pinyin, words, cards) -> list[str]  # the pinyin check
read_removed(path) -> dict[str, list[str]]  # the removed list ({} if missing)
layout_pinyin(sentence, pinyin) -> str   # the saved pinyin line
```
**One word, during the quiz** (ADR 0011, used by `live_sentences`):
```python
write_one(card, cards, vocab=None, ask=ask_claude, timeout=30, log=LIVE_LOG_FILE) -> WrittenSentences
```
One Claude call for one word (the same prompt, its band's allowed words), no retries. It returns `WrittenSentences(sentences, model)`: the sentences that pass all three checks, laid out (at most 2, repeats dropped), or `[]` if none pass or the reply isn't the JSON asked for. A `ClaudeError` goes up. One log line (`cards` 1, `retry` 0). It writes nothing to `sentences.jsonl`: banking is `sentence_bank`'s job. It doesn't read the removed list: `live_sentences` asks the bank (`is_removed`) before showing or banking.

Command line: `uv run python -m hsk_trainer.blocks.sentence_writer --limit 20 [--dry-run] [--chunk-size N] [--retries N]`. On an error it prints `Stopped: …` and exits 1.

**The prompt** (`PROMPT_VERSION = "2"`, model `sonnet`): one band per call. It gives the band's **allowed word list** (every HSK word at or below that band), then each word (hanzi, pinyin, meanings), and asks for **2** short, natural sentences per word: the word as written, only allowed words, Chinese characters and Chinese punctuation only, no names or digits, 3–20 characters, each with its **pinyin** (tone marks, one syllable per Chinese character, 儿 as `r`, the dictionary tone with no tone changes for 一 / 不, the mark left off only where the dictionary writes a neutral tone) and an English translation. Reply as JSON only: `{"cards": [{"id": "...", "sentences": [{"hanzi": "...", "pinyin": "...", "english": "..."}]}]}` (a ```` ```json ```` fence is fine). The shape is also forced with a JSON schema (`claude -p --json-schema`) and still checked afterwards.

**Order:** one band at a time, lowest first; within a band, words go in `cards.jsonl` order, `chunk_size` per call.

**The removed list** (ADR 0015): read once, before any call (also in a dry run). A sentence on it for that word is treated as failing, with the reason "an audit removed this sentence; write a different one", so it's never saved and a word left with none is retried with that reason. `sentence_bank` imports `REMOVED_FILE`, `RemovedListError` and `read_removed` from here (this block already holds the shared file helpers; `sentence_bank` imports `sentence_writer`, so the other way round would be a loop).

**Retries:** a word with no passing sentence is asked again, with its failed sentences (and their pinyin) and the reasons from the checks ("uses 一起 (band 2) …", or a pinyin reason), up to `retries` rounds (one follow-up call per band per round, split by `chunk_size` if more words fail). Words missing from the reply, or from a reply that isn't the JSON asked for, are retried the same way ("no usable sentences came back").

## Outputs
1. **`data/generated/sentences.jsonl`** (committed): one line per word that has at least one passing sentence:
   `{"id": "爸爸", "hanzi": "爸爸", "sentences": [{"hanzi": "我爸爸是医生。", "pinyin": "wǒ bà ba shì yī shēng。", "english": "My dad is a doctor."}], "model": "...", "prompt_version": "2"}`.
   Up to 2 sentences per call, each passed by the checker, the pinyin check and the English check. A line may hold up to `MAX_SAVED` (10) sentences: the quiz's bank adds sentences written during play (ADR 0011, `sentence_bank`), and such a line still counts as done. Saved after every Claude call, in `cards.jsonl` order.
2. **`data/generated/sentence_writer_log.jsonl`** (committed, appended): one line per call: `time`, `model`, `prompt_version`, `cards`, `retry` (the round: 0 for the first call, then 1, 2…), `input_tokens`, `output_tokens`, `cost_usd`.
3. **`data/live_sentence_log.jsonl`** (gitignored, appended): `write_one`'s log, same fields (`cards` 1, `retry` 0). Kept apart so playing never changes the repo; a failed log write is skipped.
4. **`WrittenSentences`** (`write_one`): `sentences` (at most 2, passing, laid out) and `model`.
5. **`SentenceRun`** summary (and on screen): `written`, `skipped` (already have a current, passing line), `failed` (ids with no passing sentence after all retries, or in a failed call), `input_tokens`, `output_tokens`.

**English translation** (checked by script): 1–120 characters, ASCII letters, digits, spaces and normal punctuation (`.,!?'"():;/%&-`), at least one letter. Curly quotes, dashes and `…` are made plain first (and saved plain).

**Pinyin** (ADR 0010): Claude writes it; `pinyin_problems` checks it. The syllables are the runs of letters (with tone marks) in Claude's text; anything else is ignored. Compared without case, with `v` read as `ü`. Tone numbers (`wo3`) are refused ("pinyin uses tone numbers…"). A tone mark may be left off (neutral tone) only where the reading itself is neutral: our dictionary already writes the real neutral tones (`bà ba`, `péng you`), so `lǎo shi` for 老师 (`lǎo shī`) fails. A looser rule was tried and `/code-review` showed it let wrong pinyin pass (他来了 `tā lai le`). The cost: a light reading the dictionary doesn't write (`jiā li`) is retried with the dictionary tone; a full tone where the dictionary has a neutral one is fine (`duì bù qǐ` for `duì bu qǐ`). 儿 after a word is its own syllable `r`, as the dictionary writes it (`nǎ r`).
   1. **One syllable per Chinese character** ("pinyin 'wǒmen zǒu ba' has 3 syllables for 4 Chinese characters …", plus "write 儿 as its own syllable r (nǎ r)" when the sentence has 儿).
   2. **HSK words** in the checker's reading (`words`, from `SentenceCheck.words`): the word's syllables match one of the readings in our dictionary pinyin (`"biàn yí / pián yi"` → either) ("pinyin bian ya for 便宜 isn't one of its readings: biàn yí / pián yi").
   3. **Every other character:** the syllable is one of `pypinyin`'s possible readings of it ("pinyin huǒ for 水 isn't a reading of 水: shuǐ").

   `layout_pinyin` makes the saved line from Claude's syllables: one per Chinese character, spaces between syllables, the sentence's own punctuation with no space around it (`wǒ chī fàn，bà ba chī fàn！`). Claude's letters are kept as written (case too), except `v` becomes `ü`. ⚠️ The check can't tell which of two real readings fits (`cháng` / `zhǎng` for 长): that's Claude's call, spot-checked by the user and the `data-auditor` (Step 6).

**Picks up where it left off, never shrinks:** first, sentences on the removed list are taken out of every saved line (the file is rewritten, except in a dry run); a line left with none is dropped, so its word needs sentences again. This is the one way a run shrinks the file, as `sentence_bank.remove` would have. Then a word with a line whose `prompt_version` is current and whose sentences all still pass the checks (sentence, pinyin, English) is skipped. Any other saved line stays until a new passing line replaces it. A line for a word no longer in `cards.jsonl` is dropped with a warning.

## Tools
- `quizkit.claude.ask_claude` (no tools for Claude, empty folder, subscription).
- `hsk_trainer.blocks.sentence_validator` (`Vocab`, `check_sentence`): the checker. Its `words` give the word-by-word reading the pinyin check uses.
- Shared with `sentence_bank`: `read_lines(path)` (reads the file; `SentenceFileError` names a bad line) and `write_lines(path, lines)` (the one way the file is written, atomically).
- `pypinyin` (`heteronym=True`: every possible reading of a character), `quizkit.files.write_atomically` and `load_cards`, pydantic.

## Failure modes
| Situation | What it does |
|---|---|
| `claude` missing / not logged in, a timeout, or a Claude error | Work so far is saved, then the `ClaudeError` goes up; the command line prints it. Re-running continues |
| Reply isn't the JSON asked for | Reported; that call's words are retried like missing words; the run goes on |
| Reply misses a word or adds one | Missing → treated as all failed (retried); extra → ignored |
| A sentence fails the checker, the pinyin check or the English check | That sentence is dropped; if none are left for the word, it's retried with the reasons |
| Claude sends more than 2 sentences | The first 2 that pass are kept |
| Still no passing sentence after `retries` | The word is listed in `failed`; no line written (an old line stays) |
| A saved line can't be read | `SentenceFileError` (a `ValueError`) naming the line, before any call; nothing changed |
| `--dry-run` | Never calls Claude, never writes |
| The removed list can't be read (broken JSON, wrong shape) | `RemovedListError` (a `SentenceFileError`) naming the file, before any call; nothing changed. The command line prints `Stopped: …` |
| Claude writes a sentence on the removed list | Treated as failing ("an audit removed this sentence…"); retried like any failing sentence |
| A saved line holds removed sentences | They're taken out (file rewritten); a line left empty is dropped and its word redone |
| `limit` < 0, `chunk_size` < 1, `retries` < 0, or no cards | `ValueError` |
| A word is listed twice in the saved file | The first copy that passes the checker is kept (else the first); warning |
| Claude sends the same sentence twice for a word | Kept once (a second copy with different pinyin is still tried) |
| `cards.jsonl` missing (command line) | Prints `Stopped: …`, exits 1 |
| `write_one`: reply isn't the JSON asked for, or misses the word | `WrittenSentences` with `[]` (no retry) |
| `write_one`: a `ClaudeError` | Goes up (no retry, nothing saved); `live_sentences` counts it as a failure |
| `write_one`: the log can't be written | Skipped; the sentences are still returned |

## How to test
- `tests/blocks/test_sentence_writer.py`, all with a **fake Claude** (never the real one) and `tmp_path` files, on a small toy deck: good reply → line written with Claude's pinyin laid out; a failing sentence is retried with its reasons in the prompt; still failing after `retries` → `failed`, no line; partly good (1 of 2 passes) → 1 kept; bad JSON; missing / extra words; English check; resume (skip current passing lines, redo old `prompt_version`, keep old line until replaced); never shrinks; dropped word warning; `--limit`, `--dry-run`; `ClaudeError` keeps work; log lines; the prompt holds the band's allowed words and one band per call. The removed list: a removed sentence in a reply isn't saved and its word is retried with the reason; a saved line with a removed sentence loses it (the rest kept, still skipped); a line of only removed sentences is dropped and redone; a dry run reads the list but writes nothing; a missing list = empty; a broken list raises `RemovedListError` before any call.
- `pinyin_problems`: right count; an HSK word's dictionary reading passes, either reading of a several-reading word passes (便宜), a made-up syllable fails with its reason; the neutral tone only where the reading is neutral (老师 `lǎo shi` fails), a full tone for a neutral dictionary syllable, tone numbers refused, 儿 as `r`, `v` for `ü` and capitals; a non-HSK character checked against pypinyin. `layout_pinyin`: spaces and punctuation. A bad-pinyin sentence is retried with the reason.
- `write_one`: one call, no retry; failing sentences dropped; at most 2; repeats; broken replies and a missing word give `[]`; `ClaudeError` goes up; one log line; `sentences.jsonl` untouched; `timeout` passed on; a ready `vocab` used; a log that can't be written is skipped.
- **Manual:** the trial run (PR 4): 20 band-1 words, the user reviews them.
