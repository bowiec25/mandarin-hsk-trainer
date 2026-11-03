# 0009: The sentence checker reads sentences with our own word list, not `jieba`

- **Status:** Accepted (2026-11-03)
- **In plain words:** ADR 0008 said the checker would split sentences into words with the `jieba` library. It doesn't: it tries every way of reading the sentence with our HSK word list and keeps the reading with the fewest problems. A sentence passes if a learner at that band could read it. This replaces that one part of ADR 0008; the rest stands.

## Context
- Written Chinese has no spaces, so a program must decide where words start and end. `jieba` makes **one** guess per sentence.
- Built and tested on 2026-11-03 (M4 Step 5), that single guess rejected good sentences: 「他一起来了」 was read as 一 / 起来 (band 2), and 「我看见他了」 failed for 看 because 看见 was read as one word.
- Measured: if any easy reading counts, 41 harder words could appear in band-1 sentences, all built from easy words a learner can read (男人 = 男 + 人, 外国 = 外 + 国).

## Decision
- **Readable at the band (the user's choice "B"):** the checker searches all readings of the sentence as HSK words, extra words or single unknown characters, keeps the one with the fewest problems (then the fewest words), with the card's word standing on its own, and reports that reading's problems.
- **`jieba` is not a dependency.** No word-splitting library is used.

## Why / alternatives considered
- **Trust `jieba` (ADR 0008 as written):** strict, but good sentences fail and short common words (看, 好) struggle to get any, which works against the 95% bar.
- **Read with all words, flag hidden harder words:** stops 男人 in a band-1 sentence, but those words are see-through, and the rule still depends on which reading is picked.

## Consequences
- ✅ Fewer false rejections, so fewer retries; one less library.
- ✅ Every reason names the word and its band, as before.
- ⚠️ See-through compounds of easy words (男人, 回来) count as readable. The user's spot-check and the `data-auditor` (Step 6) can flag any that feel too hard.
