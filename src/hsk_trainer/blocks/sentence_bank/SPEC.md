# Block: `sentence_bank`

> **In plain words:** Keep the bank of checked example sentences: pick, for a word, a new or a banked sentence by the ADR 0011 rule, remember when each was seen, and add new ones.

## Goal
Keep the bank of checked example sentences: pick, for a word, a new or a banked sentence by the ADR 0011 rule, remember when each was seen, and add new ones.

It exists so the quiz's sentence modes (`char_sentence`, `full`) have a sentence to show, and so sentences written live during play (next PR) are kept and reused (ADR 0011). The bank is `data/generated/sentences.jsonl`, the same file and format `sentence_writer` writes.

**Not in scope:** writing or checking sentences (`sentence_writer`, `sentence_validator`: a sentence is checked *before* it's added); asking Claude during the quiz (the live PR); showing anything on screen (the CLI).

## Kind
**script.** Every job is plain bookkeeping that code can check: count a word's sentences, apply a fixed formula, sort by a time, append to a file. No language judgment (ADR 0002).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `cards` | `list[Card]` | All the cards: the bank keeps its lines in `cards.jsonl` order and ignores lines for other ids |
| `path` | `Path` (default `SENTENCES_FILE`) | The bank, `data/generated/sentences.jsonl` (committed). Missing = an empty bank |
| `seen_path` | `Path` (default `SEEN_FILE`) | When each sentence was last shown, `data/sentence_seen.json` (gitignored, like `progress.db`) |
| `settings` | `BankSettings` | `floor: float = 0.2` (0–1), `cap: int = 10` (1 to `sentence_writer.MAX_SAVED` = 10: a longer line would look broken to the writer, which would redo it and lose the banked sentences) |
| `rng` | `random.Random` | For the new-or-banked draw; tests pass a seeded one |
| `now` | function | Gives the current time, with a timezone (default `datetime.now(UTC)`); tests pass a fake clock |

**How it's called** (importable from `hsk_trainer.blocks.sentence_bank`):
```python
bank = SentenceBank(cards, path=SENTENCES_FILE, seen_path=SEEN_FILE,
                    settings=BankSettings(), rng=None, now=None)
bank.count(card_id) -> int              # banked sentences for the word
bank.chance_of_new(card_id) -> float    # max(floor, 1 / (1 + count))
bank.wants_new(card_id) -> bool         # one draw: rng.random() < chance_of_new
bank.banked(card_id) -> Sentence | None # the least recently seen (never seen first)
bank.mark_seen(card_id, sentence)       # remember it was shown now
bank.add(card_id, sentence, model) -> bool  # save a new (already checked) sentence
```

## Outputs
1. **`chance_of_new` / `wants_new`** (ADR 0011): 0 banked → 1.0 (always new), 1 → 0.5, 3 → 0.25, 4 or more → `floor` (0.2).
2. **`banked`**: a `Sentence` (`hanzi`, `pinyin`, `english`, from `sentence_writer`) or `None` if the word has none. The pick is the sentence whose last-seen time is oldest; never-seen sentences come first, in file order.
3. **`data/sentence_seen.json`** (written by `mark_seen`, atomically, after merging with what's in the file, so two quizzes at once keep both histories; the later time wins): `{"<card id>": {"<sentence hanzi>": "<ISO time>"}}`.
4. **`data/generated/sentences.jsonl`** (written by `add`, atomically): the sentence joins the word's line (a new line is made if the word has none, with `sentence_writer.PROMPT_VERSION`; the line's `model` becomes the newest sentence's model). Returns `True` if added; `False` if that hanzi is already banked for the word, or the word already has `cap` sentences. Lines stay in `cards.jsonl` order; then every other line (other ids, a second copy of an id) as it was, in file order: the file never shrinks.

## Tools
- `hsk_trainer.blocks.sentence_writer`: `SENTENCES_FILE`, `Sentence`, `SentenceLine`, `read_lines` (the file reader; raises `SentenceFileError`), `write_lines` (the one file writer), `MAX_SAVED`, `PROMPT_VERSION`.
- `quizkit.files.write_atomically`, `random`, `json`, pydantic.

**Known limit:** `sentence_writer` replaces a word's whole line when it redoes it (after a `PROMPT_VERSION` bump, or when any one saved sentence fails its checks), which would drop sentences banked from play. It also drops lines for ids that are no longer cards: "never shrinks" holds within the bank. Today every line is current, so nothing is redone; see `docs/FUTURE.md`.

## Failure modes
| Situation | What it does |
|---|---|
| Bank file missing | An empty bank: `count` 0, `banked` `None`, `chance_of_new` 1.0 |
| A bank line can't be read | `SentenceFileError` (a `ValueError`) naming the line, when the bank is made |
| The same id on two lines (only after a hand edit) | The first line is used; the second is kept as it is. `sentence_writer` keeps the first copy that passes its checks, so the two can disagree until its next run tidies the file |
| Seen file missing | Nothing seen yet |
| Seen file unreadable (bad JSON, wrong shape, a time without a timezone) | Warning; treated as nothing seen; rewritten on the next `mark_seen` |
| `card_id` not one of the cards | `ValueError` (a bug in the caller), from every method |
| `mark_seen` for a sentence not in the bank | Recorded anyway (no error) |
| The seen file can't be saved | `mark_seen` raises the `OSError`; the CLI prints one note and the quiz carries on |
| The bank file can't be read (CLI) | `Can't read the sentence bank …`, naming the line; exits 1 |
| `floor` outside 0–1, `cap` < 1 or > `MAX_SAVED` (10) | `BankSettings` rejects it (`ValidationError`) |
| `add` when the word has `cap` sentences | Returns `False`; nothing written |

**Not re-checked here:** the bank trusts its file. Every sentence is checked before it's saved (by `sentence_writer`, or by the live PR before `add`), and the real-file test checks the committed file.

## How to test
- `tests/blocks/test_sentence_bank.py`, with `tmp_path` files, a toy deck, a seeded `rng` and a fake clock: the chance for 0 / 1 / 3 / 4+ sentences and a custom floor; `wants_new` follows `rng` (e.g. always new at 0); `banked` picks never-seen first, then the oldest seen; `mark_seen` is saved and read back by a new bank; `add` appends, makes a new line, refuses a duplicate and a full word, keeps cards order and other ids, writes atomically; every failure mode.
- `sentence_writer` with more than 2 banked sentences on a line: still "done" (up to `cap`), never replaced.
- **CLI** (`tests/test_cli.py`): `char_sentence` and `full` now play. The sentence is shown under the word (with its pinyin in `full`), its English after the answer, "no example sentence yet" for a word without one, and the seen file is updated.
