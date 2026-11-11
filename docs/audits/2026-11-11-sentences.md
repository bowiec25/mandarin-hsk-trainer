# Sentence bank audit: 2026-11-11 (new live sentences)

> **In plain words:** while the user played the new web page, live sentences added 4 words (8 sentences) to the bank. The read-only `data-auditor` checked just those ("only new"). It flagged 1 sentence, which was removed. This is the first audit under ADR 0015: flagged sentences are removed without asking anyone.

- **Bank:** `data/generated/sentences.jsonl`, now 27 words, **47 sentences** (the 40 of 2026-11-10, plus 8 new, minus 1 removed).
- **Checks:** natural, English, reading, level, sense (see `.claude/agents/data-auditor.md`).
- **Flags:** 1.

| Word | Sentence | Check | Why | Done |
|---|---|---|---|---|
| 国 | 这个国很大。 | natural | 国 almost never stands alone after 这个; a native speaker says 这个国家很大 (the writer likely avoided 国家, a band-3 word) | **removed** |

- **Formatting (not errors, tidied):** 你是哪国人？ had pinyin starting with a capital ("Nǐ shì…"); now lowercase, like the rest of the bank. A script check for this is in `docs/FUTURE.md`.
- **Notes from the auditor (no action):**
  - 有点儿 is written "yǒu diǎn r", matching the word's own pinyin in `cards.jsonl`. No other sentence has 儿 yet, so there's no bank style to match.
  - 他是中国人 writes "zhōng guó" in lowercase, as the bank does elsewhere ("hàn yǔ").
- **Result:** 国 keeps 1 sentence (你是哪国人？); the other 3 words keep 2 each.

## Audited
国 · 这个国很大。
国 · 你是哪国人？
人 · 这里有很多人。
人 · 他是中国人。
谢谢 · 谢谢你！
谢谢 · 谢谢老师，再见。
有点儿 · 今天有点儿冷。
有点儿 · 我有点儿忙。
