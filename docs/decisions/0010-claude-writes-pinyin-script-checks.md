# 0010: Sentence pinyin: Claude writes it, a script checks it

- **Status:** Accepted (2026-11-04)
- **In plain words:** ADR 0008 said a script makes the pinyin under each example sentence. The trial run showed the script guesses wrong for words with more than one reading (便宜 came out `biàn yí`, should be `pián yi`). Now Claude writes the pinyin with each sentence, and a script checks every syllable is a real reading of that character (and of that word, for HSK words). This replaces part 3 of ADR 0008; the rest stands.

## Context
- Trial run (M4 Step 5, 2026-11-04, 20 band-1 words, 38 sentences): 2 sentences had wrong pinyin, both from words with several readings: 不便宜 → `bù biàn yí`, 东西 ("thing") → `dōng xī` (should be `dōng xi`).
- 152 of the 978 HSK words have more than one reading (`readings` in `cards.jsonl`), and pypinyin's guess for them can't be checked by code.
- Choosing the right reading needs the sentence's meaning: language judgment, so an agent's job (ADR 0002), as long as a script checks the result.

## Decision
- With each sentence Claude also writes its **pinyin**: tone marks, one syllable per Chinese character, the dictionary tone (no tone changes for 一 / 不), neutral tone without a mark.
- A script checks it, and a sentence that fails goes back to Claude with the reason, like any other check:
  1. one syllable per Chinese character;
  2. for each HSK word in the checker's reading: its syllables match one of **our dictionary's readings** of that word (a syllable may also be written in the neutral tone);
  3. for every other character: the syllable is one of **pypinyin's possible readings** of that character (or its neutral-tone form).
- The saved pinyin is Claude's syllables, laid out by script (spaces between syllables, the sentence's own punctuation).
- `PROMPT_VERSION` goes to `"2"`, so the trial lines are written again.

## Why / alternatives considered
- **Keep pypinyin and flag the 152 words for review:** free, but a person must check every flagged sentence, and the learner still sees wrong pinyin until then.
- **Our dictionary only:** it has every reading of a word but not which one fits the sentence.
- **Trust Claude's pinyin unchecked:** breaks ADR 0002. Claude can make up a reading; the script stops that.

## Consequences
- ✅ The right reading for words like 便宜, 东西, 长, picked from the sentence's meaning, and never a made-up sound.
- ✅ Wrong pinyin becomes a retry with a reason, not a silent mistake.
- ⚠️ The script can't tell *which* of two real readings is right (`cháng` vs `zhǎng` both pass for 长); that is still Claude's call, checked by the user's spot-check and the `data-auditor` (Step 6).
- ⚠️ A little more output per call (the pinyin), so slightly more tokens.
