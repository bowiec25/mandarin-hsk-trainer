# Block: `sentence_validator`

> **In plain words:** Check one example sentence for a word: the word is in it, a learner at the word's band could read every other word, and it is short; give reasons for any failure.

## Goal
Check one example sentence for a word: the word is in it, a learner at the word's band could read every other word, and it is short; give reasons for any failure.

It exists so no sentence reaches the quiz unchecked (ADR 0002, ADR 0008): Claude writes sentences, this script decides whether they're easy enough. Its reasons are plain English, so `sentence_writer` can send them back to Claude ("uses 一起, which is band 2").

**Not in scope:** whether a sentence is *natural* or *true* (that needs judgment: the user's spot-check and the `data-auditor` subagent, Step 6); making the pinyin (the writer PR).

## Kind
**script.** Every rule can be checked by code: is the word there, can the rest be read with words at a low enough band, how long is it. Free and instant, so it can check all ~2,000 sentences on every run.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `vocab` | `Vocab` | Built once from all the cards (`Vocab(cards)`, `data/processed/cards.jsonl`): every word's `hanzi` and band |
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
- `min_chars: int = 3`, `max_chars: int = 20`: counted in Chinese characters, punctuation not counted
- `extra_words: tuple[str, ...] = ()`: words always allowed (empty for now; set from the trial run if needed)

Spaces at the start and end are trimmed first. **The rules** (every rule is always checked, so all problems are reported at once):
1. **Only Chinese characters and Chinese punctuation.** Chinese characters include 〇. Punctuation = any non-ASCII punctuation mark (Unicode category P, e.g. `，。？！、：；“”‘’…—《》（）「」『』【】`) plus `·` and `～`. No Latin letters (incl. full-width ones), digits, ASCII punctuation or spaces.
2. **The word is in it** (as written).
3. **Length** between `min_chars` and `max_chars`.
4. **A learner at this band could read it** (the user's choice "B", 2026-11-03). The checker tries every way of reading the sentence as a row of words and keeps the reading with the **fewest problems** (then the fewest words). If the word is in the sentence, **the word itself must be one of the words**. In that reading:
   - an HSK word at or below the card's band, or an extra word → fine;
   - an HSK word above the band → a problem: "uses 一起 (band 2) …";
   - a character that isn't part of any HSK word → a problem: "uses 猫, not an HSK word …".

   So 吃饭 reads as 吃 + 饭, and 男人 as 男 + 人: built from easy words, so fine for band 1 (measured: 41 harder words are built from band-1 words this way, all of them see-through like 外国, 回来). This doesn't depend on one guess of where words start and end: `jieba` was tried first (ADR 0008) and dropped, because `/code-review` showed its single guess rejected good sentences (「我看见他了」 for 看).

   **The word only inside a longer word** (学 in 学校, 我 in 我们): if reading the word on its own makes things worse than reading it inside a longer word, the reason says so ("has 学 only inside 学校, not on its own"), rather than blaming the leftover character.

## Outputs
**`SentenceCheck`** (pydantic, frozen), returned in memory:
| Field | Type | Plain meaning |
|---|---|---|
| `passed` | `bool` | True only if every rule passes |
| `reasons` | `tuple[str, ...]` | One plain-English line per problem, e.g. `"uses 一起 (band 2); a sentence for a band-1 word may only use band 1"`. Empty when passed |
| `words` | `tuple[str, ...]` | The reading it chose, word by word (punctuation left out), so a person can see why |

Reasons name the word and its band (or "not an HSK word"), so the writer can pass them straight to Claude.

## Tools
- Plain Python: one small dynamic-programming search over the sentence (no word-splitting library), and `unicodedata` for punctuation.
- **pydantic**: `SentenceSettings`, `SentenceCheck`.
- `quizkit.models.Card`. No files, no network, no agent.

## Failure modes
| Situation | What it does |
|---|---|
| A sentence breaks one or more rules | `passed=False`, one reason per problem (not an error) |
| Empty or blank sentence | `passed=False`, with the single reason "empty sentence" (the other rules are skipped) |
| `word` isn't one of the cards | **Raises `ValueError`** (a bug in the caller, not a bad sentence) |
| `cards` is empty, or two cards share a `hanzi` | **Raises `ValueError`** when `Vocab` is made |
| A card's word has a non-Chinese character (e.g. a future `T恤`) | Works: the word is matched as written |
| `min_chars` < 1 or `max_chars` < `min_chars` | `SentenceSettings` **rejects** it (`ValidationError`) |
| The same word appears twice in a sentence | Fine; checked once each time it appears |

## How to test
- `tests/blocks/test_sentence_validator.py`, mostly a **toy vocab** (a handful of hand-made cards at bands 1–3), so each rule is tested on its own: pass; word missing (other problems still reported); a band-2 word in a band-1 sentence; a band-2 word allowed in a band-3 sentence; words built from easy words pass (吃饭, 电视 as 电 + 视); an unknown character fails; the reading with the fewest problems wins; the word only inside a longer word; Latin / full-width letters, digits and ASCII punctuation fail, Chinese punctuation passes; too short / exactly 3 / too long, 〇 counted; several problems → several reasons; extra words; settings validation; every error case.
- **Real data:** with the real `cards.jsonl`, hand-written band-1 sentences pass (`我们去学校吃饭。`, `妈妈在家看电视。`, `你叫什么名字？`, `我看见他了。`, `你好吗？`) and `明天下午我们一起喝茶吧。` fails for a band-1 word because of 一起 (band 2).
