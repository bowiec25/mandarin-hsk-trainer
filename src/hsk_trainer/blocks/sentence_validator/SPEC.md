# Block: `sentence_validator`

> **In plain words:** Check one example sentence for a word: the word is in it, every other word is at or below the word's band, and it is short; give reasons for any failure.

## Goal
Check one example sentence for a word: the word is in it, every other word is at or below the word's band, and it is short; give reasons for any failure.

It exists so no sentence reaches the quiz unchecked (ADR 0002, ADR 0008): Claude writes sentences, this script decides whether they're easy enough. Its reasons are plain English, so `sentence_writer` can send them back to Claude ("uses 一起, which is band 2").

**Not in scope:** whether a sentence is *natural* or *true* (that needs judgment: the user's spot-check and the `data-auditor` subagent, Step 6); making the pinyin (the writer PR).

## Kind
**script.** Every rule can be checked by code: is the word there, is each other word on the list at a low enough band, how long is it. Free and instant, so it can check all ~2,000 sentences on every run.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `cards` | `list[Card]` | All the cards (`data/processed/cards.jsonl`): each card's `hanzi` and `level` (band) |
| `sentence` | `str` | The sentence to check, e.g. `"我爸爸是医生。"` |
| `word` | `str` | The word it's for, e.g. `"爸爸"` |
| `settings` | `SentenceSettings` (pydantic) | Length limits and extra allowed words (defaults below) |

**How it's called** (importable from `hsk_trainer.blocks.sentence_validator`):
```python
vocab = Vocab(cards)  # built once: knows every word's band
check = check_sentence(sentence, word, vocab, settings=None)  # -> SentenceCheck
```
The band comes from the word's own card: a sentence for a band-1 word may only use band-1 words; for a band-3 word, bands 1–3.

**`SentenceSettings`** (frozen) defaults:
- `min_chars: int = 4`, `max_chars: int = 20`: counted in Chinese characters, punctuation not counted
- `extra_words: tuple[str, ...] = ()`: words always allowed (empty for now; set from the trial run if needed)

Spaces at the start and end are trimmed first. **The rules, in order** (all failures are reported, not just the first):
1. **Only Chinese characters and Chinese punctuation** (`，。？！、：；“”‘’`). No Latin letters, digits or spaces.
2. **The word is in it** (as written: `"爸爸" in sentence`).
3. **Length** between `min_chars` and `max_chars`.
4. **Every other word is allowed.** The sentence (minus punctuation) is split with `jieba`, which has been told every HSK word. For each piece:
   - an **HSK word** → its band must be ≤ the card's band;
   - an **extra word** → allowed;
   - **anything else** (jieba glued words together, e.g. 吃饭, 这个, 看电视) → allowed only if it can be split completely into allowed words (吃 + 饭). Otherwise it's an unknown word.

## Outputs
**`SentenceCheck`** (pydantic, frozen), returned in memory:
| Field | Type | Plain meaning |
|---|---|---|
| `passed` | `bool` | True only if every rule passes |
| `reasons` | `tuple[str, ...]` | One plain-English line per problem, e.g. `"uses 一起 (band 2); a sentence for a band-1 word may only use band 1"`. Empty when passed |
| `words` | `tuple[str, ...]` | The pieces it checked, in order (glued pieces already split), so a person can see why |

Reasons name the word and its band (or "not an HSK word"), so the writer can pass them straight to Claude.

## Tools
- **`jieba`**: splits Chinese into words. Uses its **own** `jieba.Tokenizer` (not the global one), with every HSK word added, so other code is unaffected.
- **pydantic**: `SentenceSettings`, `SentenceCheck`.
- `quizkit.models.Card`. No files, no network, no agent.

## Failure modes
| Situation | What it does |
|---|---|
| A sentence breaks one or more rules | `passed=False`, one reason per problem (not an error) |
| Empty or blank sentence | `passed=False`, with the single reason "empty sentence" (the other rules are skipped) |
| `word` isn't one of the cards | **Raises `ValueError`** (a bug in the caller, not a bad sentence) |
| `cards` is empty, or two cards share a `hanzi` | **Raises `ValueError`** when `Vocab` is made |
| `min_chars` < 1 or `max_chars` < `min_chars` | `SentenceSettings` **rejects** it (`ValidationError`) |
| The same word appears twice in a sentence | Fine; checked once each time it appears |

## How to test
- `tests/blocks/test_sentence_validator.py`, mostly a **toy vocab** (a handful of hand-made cards at bands 1–3), so each rule is tested on its own: pass; word missing; a band-2 word in a band-1 sentence; a band-2 word allowed in a band-3 sentence; glued pieces that split into allowed words pass (吃饭); glued pieces that don't, fail as unknown; Latin letters / digits fail; too short / too long; several problems → several reasons; extra words; settings validation; every error case.
- **Real data:** with the real `cards.jsonl`, hand-written band-1 sentences pass (`我们去学校吃饭。`, `妈妈在家看电视。`, `你叫什么名字？`) and `明天下午我们一起喝茶吧。` fails for a band-1 word because of 一起 (band 2). These come from the jieba measurement on 2026-11-03.
