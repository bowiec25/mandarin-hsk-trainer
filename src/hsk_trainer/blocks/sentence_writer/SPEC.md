# Block: `sentence_writer`

> **In plain words:** Ask Claude for 1-2 short example sentences per word, keep only the ones the sentence checker passes (retrying failures with its reasons), add pinyin by script, and save them to data/generated/sentences.jsonl.

## Goal
Ask Claude for 1-2 short example sentences per word, keep only the ones the sentence checker passes (retrying failures with its reasons), add pinyin by script, and save them to data/generated/sentences.jsonl.

It exists to unlock the quiz modes `char_sentence` and `full` (ADR 0008): a word is easier to learn in a sentence. It runs **offline, as a batch**, before anyone studies; the quiz only reads the file.

**Not in scope:** reading the file for the quiz (PR 5, the wiring); judging whether a sentence is natural (the user's spot-check, then the `data-auditor` subagent in Step 6).

## Kind
**agent.** Writing a natural sentence from a small word list needs language skill (ADR 0002). As ADR 0002 requires: a script checks every sentence (`sentence_validator`, ADR 0009), it has `--limit` / `--dry-run`, and it logs the model, prompt version and tokens. Same shape as `answer_writer`.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `cards` | `list[Card]` | **All** the cards (`cards.jsonl`): hanzi, pinyin, band, dictionary meanings. Always the whole deck: it is also the checker's word list (a trial uses `limit`, not fewer cards) |
| `limit` | `int \| None` | Only the first N words that still need sentences (trial: `--limit 20`) |
| `dry_run` | `bool` | Show the first prompt; never call Claude, never write a file |
| `chunk_size` | `int` (default 20) | Words per Claude call (one band per call) |
| `retries` | `int` (default 2) | Extra tries for a word whose sentences all failed the checker |
| `ask` | function | Calls Claude. Default `quizkit.claude.ask_claude` (`claude -p`, no tools). Tests pass a fake |

**How it's called** (importable from `hsk_trainer.blocks.sentence_writer`):
```python
write_sentences(cards, limit=None, dry_run=False, chunk_size=20, retries=2,
                ask=ask_claude, out=SENTENCES_FILE, log=LOG_FILE) -> SentenceRun
sentence_pinyin(sentence, cards, words=None) -> str   # the pinyin line, by script
```
Command line: `uv run python -m hsk_trainer.blocks.sentence_writer --limit 20 [--dry-run] [--chunk-size N] [--retries N]`. On an error it prints `Stopped: …` and exits 1.

**The prompt** (`PROMPT_VERSION = "1"`, model `sonnet`): one band per call. It gives the band's **allowed word list** (every HSK word at or below that band), then each word (hanzi, pinyin, meanings), and asks for **2** short, natural sentences per word: the word as written, only allowed words, Chinese characters and Chinese punctuation only, no names or digits, 3–20 characters, each with an English translation. Reply as JSON only: `{"cards": [{"id": "...", "sentences": [{"hanzi": "...", "english": "..."}]}]}` (a ```` ```json ```` fence is fine). The shape is also forced with a JSON schema (`claude -p --json-schema`) and still checked afterwards.

**Order:** one band at a time, lowest first; within a band, words go in `cards.jsonl` order, `chunk_size` per call.

**Retries:** a word with no passing sentence is asked again, with its failed sentences and the checker's reasons ("uses 一起 (band 2) …"), up to `retries` rounds (one follow-up call per band per round, split by `chunk_size` if more words fail). Words missing from the reply, or from a reply that isn't the JSON asked for, are retried the same way ("no usable sentences came back").

## Outputs
1. **`data/generated/sentences.jsonl`** (committed): one line per word that has at least one passing sentence:
   `{"id": "爸爸", "hanzi": "爸爸", "sentences": [{"hanzi": "我爸爸是医生。", "pinyin": "wǒ bà ba shì yī shēng。", "english": "My dad is a doctor."}], "model": "...", "prompt_version": "1"}`.
   Up to 2 sentences, each passed by the checker. Saved after every Claude call, in `cards.jsonl` order.
2. **`data/generated/sentence_writer_log.jsonl`** (committed, appended): one line per call: `time`, `model`, `prompt_version`, `cards`, `retry` (the round: 0 for the first call, then 1, 2…), `input_tokens`, `output_tokens`, `cost_usd`.
3. **`SentenceRun`** summary (and on screen): `written`, `skipped` (already have a current, passing line), `failed` (ids with no passing sentence after all retries, or in a failed call), `input_tokens`, `output_tokens`.

**English translation** (checked by script): 1–120 characters, ASCII letters, digits, spaces and normal punctuation (`.,!?'"():;/%&-`), at least one letter. Curly quotes, dashes and `…` are made plain first (and saved plain).

**Pinyin** (`sentence_pinyin`, ADR 0008): the sentence is read the way the checker reads it; each HSK word with one reading takes **our dictionary pinyin** (e.g. `bà ba`, neutral tones kept), anything else takes `pypinyin` (tone marks), which reads the whole sentence at once so it sees each character's context (这个 → `zhè ge`). ⚠️ Known limit: the 152 words with several readings (长, 东西, 便宜…) rely on pypinyin's guess, which can be wrong (他头发很长 → `zhǎng`, should be `cháng`). The user's trial review and the `data-auditor` (Step 6) check these. Syllables are separated by spaces; punctuation is kept as written, with no space around it (`wǒ chī fàn，bà ba chī fàn！`). `words` is the checker's reading; without it, the sentence is read as the fewest HSK words.

**Picks up where it left off, never shrinks:** a word with a line whose `prompt_version` is current and whose sentences all still pass the checker is skipped. Any other saved line stays until a new passing line replaces it. A line for a word no longer in `cards.jsonl` is dropped with a warning. The pinyin of a current, passing line is made again on every run (free), so a hand edit to it can't stick.

## Tools
- `quizkit.claude.ask_claude` (no tools for Claude, empty folder, subscription).
- `hsk_trainer.blocks.sentence_validator` (`Vocab`, `check_sentence`): the checker. Its `words` give the reading used for the pinyin.
- `pypinyin` (new dependency), `quizkit.files.write_atomically` and `load_cards`, pydantic.

## Failure modes
| Situation | What it does |
|---|---|
| `claude` missing / not logged in, a timeout, or a Claude error | Work so far is saved, then the `ClaudeError` goes up; the command line prints it. Re-running continues |
| Reply isn't the JSON asked for | Reported; that call's words are retried like missing words; the run goes on |
| Reply misses a word or adds one | Missing → treated as all failed (retried); extra → ignored |
| A sentence fails the checker or its English fails the check | That sentence is dropped; if none are left for the word, it's retried with the reasons |
| Claude sends more than 2 sentences | The first 2 that pass are kept |
| Still no passing sentence after `retries` | The word is listed in `failed`; no line written (an old line stays) |
| A saved line can't be read | `SentenceFileError` (a `ValueError`) naming the line, before any call; nothing changed |
| `--dry-run` | Never calls Claude, never writes |
| `limit` < 0, `chunk_size` < 1, `retries` < 0, or no cards | `ValueError` |
| A word is listed twice in the saved file | The first copy that passes the checker is kept (else the first); warning |
| Claude sends the same sentence twice for a word | Kept once |
| `cards.jsonl` missing (command line) | Prints `Stopped: …`, exits 1 |

## How to test
- `tests/blocks/test_sentence_writer.py`, all with a **fake Claude** (never the real one) and `tmp_path` files, on a small toy deck: good reply → line written with pinyin; a failing sentence is retried with its reasons in the prompt; still failing after `retries` → `failed`, no line; partly good (1 of 2 passes) → 1 kept; bad JSON; missing / extra words; English check; resume (skip current passing lines, redo old `prompt_version`, keep old line until replaced); never shrinks; dropped word warning; `--limit`, `--dry-run`; `ClaudeError` keeps work; log lines; the prompt holds the band's allowed words and one band per call.
- `sentence_pinyin`: dictionary pinyin for HSK words (爸爸 → `bà ba`), `pypinyin` for others, punctuation kept.
- **Manual:** the trial run (PR 4): 20 band-1 words, the user reviews them.
