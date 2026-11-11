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
| `removed_path` | `Path` (default `REMOVED_FILE`) | Sentences an audit removed, `data/generated/sentences_removed.json` (committed): never banked, shown or added again (ADR 0015). Missing = nothing removed |
| `settings` | `BankSettings` | `floor: float = 0.2` (0–1), `cap: int = 10` (1 to `sentence_writer.MAX_SAVED` = 10: a longer line would look broken to the writer, which would redo it and lose the banked sentences) |
| `rng` | `random.Random` | For the new-or-banked draw; tests pass a seeded one |
| `now` | function | Gives the current time, with a timezone (default `datetime.now(UTC)`); tests pass a fake clock |

**How it's called** (importable from `hsk_trainer.blocks.sentence_bank`):
```python
bank = SentenceBank(cards, path=SENTENCES_FILE, seen_path=SEEN_FILE,
                    removed_path=REMOVED_FILE, settings=BankSettings(), rng=None, now=None)
bank.count(card_id) -> int              # banked sentences for the word (removed ones don't count)
bank.is_removed(card_id, hanzi) -> bool # on the removed list?
bank.remove(card_id, hanzi) -> bool     # an audit's removal: off the bank, onto the list
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
4. **`data/generated/sentences.jsonl`** (written by `add`, atomically): the sentence joins the word's line (a new line is made if the word has none, with `sentence_writer.PROMPT_VERSION`; the line's `model` becomes the newest sentence's model). Returns `True` if added; `False` if that hanzi is already banked for the word, is on the removed list, or the word already has `cap` sentences. Lines stay in `cards.jsonl` order; then every other line (other ids, a second copy of an id) as it was, in file order: the file never shrinks, except through `remove`.
5. **The removed list** (ADR 0015). An audit removes a sentence with `remove(card_id, hanzi)`, not by editing the file by hand:
   - the hanzi goes onto the list `data/generated/sentences_removed.json`, `{"<card id>": ["<sentence hanzi>", …]}` (written atomically, first, so a crash in between leaves it listed: still never shown);
   - it's taken out of the word's line in the bank (written atomically); a line left with no sentences is dropped, so the word counts as having none (`sentence_writer` sees it as not done yet);
   - returns `True` if it was in the bank, `False` if it wasn't (it's still listed). Listing it twice does nothing.

   Matching is by the sentence's hanzi, exactly, for that word (as for repeats). A listed sentence still in the file (e.g. written back by `sentence_writer`) is skipped: `count`, `chance_of_new` and `banked` act as if it weren't there, and the file isn't changed just for that.

   Small rules:
   - **"In the bank"** means a sentence the bank would use: in the word's line and not listed. So `remove` of a sentence that's listed but still in the file takes it out of the file and returns `False` (it was already out of use).
   - **`add` tidies the word's line:** when it rewrites a line, listed sentences still in it are dropped. So `cap` counts only usable sentences, and a line never grows past `cap` (more than `MAX_SAVED` would make `sentence_writer` redo the line and lose banked sentences).
   - **`remove` when the bank file is missing** only writes the list; it doesn't create the bank file.
   - **`remove` merges with the list on disk** before writing (as `mark_seen` does), so a removal made meanwhile by another bank (an audit, another quiz) is kept.
   - **Known limits:** a quiz already running when an audit removes a sentence keeps its own copy of the bank and list, so it may still show that sentence, or write it back into the file with its next `add`, until it ends; the list stays right, so the next bank skips it. (`sentence_writer`, the batch writer, reads the list too since #77: it never saves a listed sentence. `REMOVED_FILE`, `RemovedListError` and the reader live there, imported here.)
   - A listed id that is no longer a card is fine (kept as it is).
   - `remove` works on the word's first line only. A second copy of the id (only after a hand edit) is kept as it is, so after `remove` empties the first line, a new bank reads the second copy as the word's line. Listed sentences in it are still skipped.

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
| `add` of a sentence on the removed list | Returns `False`; nothing written |
| Removed list missing | Nothing removed |
| Removed list unreadable (bad JSON, not an object of lists of strings) | `RemovedListError` (a `SentenceFileError`) naming the file, when the bank is made (it's committed data, like the bank: loud, not ignored). The quiz says `Can't read the removed-sentences list …` |
| `remove` of a sentence not in the bank | Listed anyway; returns `False` |
| `remove` / `is_removed` with an unknown `card_id` | `ValueError`, as for every method |
| The removed list or the bank can't be saved during `remove` | The `OSError` goes up (an audit is a batch job: it should stop) |

**Not re-checked here:** the bank trusts its file. Every sentence is checked before it's saved (by `sentence_writer`, or by the live PR before `add`), and the real-file test checks the committed file.

## How to test
- `tests/blocks/test_sentence_bank.py`, with `tmp_path` files, a toy deck, a seeded `rng` and a fake clock: the chance for 0 / 1 / 3 / 4+ sentences and a custom floor; `wants_new` follows `rng` (e.g. always new at 0); `banked` picks never-seen first, then the oldest seen; `mark_seen` is saved and read back by a new bank; `add` appends, makes a new line, refuses a duplicate and a full word, keeps cards order and other ids, writes atomically; the removed list (`remove` takes a sentence off the bank and lists it, drops an emptied line, keeps other words and lines; `add`, `banked` and `count` skip listed sentences, also ones still in the file; a new bank reads the list back; a missing list; a broken list raises); every failure mode.
- `sentence_writer` with more than 2 banked sentences on a line: still "done" (up to `cap`), never replaced.
- **CLI** (`tests/test_cli.py`): `char_sentence` and `full` now play. The sentence is shown under the word (with its pinyin in `full`), its English after the answer, "no example sentence yet" for a word without one, and the seen file is updated.
