# 0008: Example sentences: Claude writes, a script checks, Claude retries; pinyin by script

- **Status:** Accepted (2026-11-03); partly superseded by [0009](0009-validator-reads-without-jieba.md) (no `jieba`: the checker reads sentences with our own word list) and [0010](0010-claude-writes-pinyin-script-checks.md) (Claude writes the pinyin, a script checks it) and [0011](0011-live-sentences-growing-bank.md) (sentences written live in the quiz, saved to a growing bank)
- **In plain words:** for each word, Claude writes 1–2 short Chinese sentences (with an English translation). A script checks each one: is the word in it, and are all the other words easy enough? Sentences that fail go back to Claude with the reason. The pinyin under each sentence is made by a script, not by Claude. This replaces the original plan's "Claude calls a `check_vocab_level` tool" (`docs/PLAN.md`), which assumed the paid API.

## Context
- `docs/PLAN.md` planned `sentence_writer` as an agent that calls a `check_vocab_level` **tool** through the Anthropic SDK's tool runner, with an API key.
- ADR 0005 moved our agents to `claude -p` under the subscription, with **no tools**. `answer_writer` (M4 Step 3) showed the alternative works: Claude writes, a script checks, and only the failures are asked again.
- Pinyin can be made by code. Measured 2026-11-03: the `pypinyin` library matches the dictionary pinyin on **744 of 826** single-reading HSK words (90.1%). The misses are style, not wrong sounds: neutral tones (`bàbà` vs `bà ba`), tone changes (`bú yào` vs `bù yào`) and 儿 (`nǎér` vs `nǎ r`). On sentences it picked the right reading for 觉 (jué / jiào), 行 (háng) and 了 (le).
- ADR 0002: if code can do it or check it, use a script.

## Decision
**1. `sentence_writer` (agent, `hsk_trainer`, an offline batch like `answer_writer`)**
- Sends cards to Claude in chunks; for each word Claude returns 1–2 sentences in characters, each with an English translation.
- Every sentence goes through the validator. Failures go back to Claude **with the validator's reasons** ("uses 银行, which is band 3"), at most 2 retries per word. Words still failing are listed in the run summary, not written.
- `--limit N` / `--dry-run`; logs model, prompt version and tokens; writes `data/generated/sentences.jsonl` (committed), never shrinking it (as `answer_writer`, ADR 0006).
- Trial on 20 band-1 words → the user reviews → full run (estimate shown first).

**2. `sentence_validator` (script, `hsk_trainer`)**
- The target word is in the sentence.
- Every other word (split with `jieba`) is allowed for the card's band: an HSK word at or below that band, plus a small fixed list of extras the SPEC names (punctuation, numbers written as characters, maybe names). Exact rules are set in its SPEC, from real sentences.
- Length limits, Chinese characters only (no Latin letters).
- It returns pass/fail **with reasons**, so the writer can feed them back.

**3. Pinyin by script**
- Words that are HSK words with one reading take **our dictionary pinyin** (neutral tones as the dictionary writes them); everything else takes `pypinyin`. No Claude, nothing to check.

**4. Bar:** at least 95% of the words get a passing sentence (PLAN.md's M4 target), plus a spot-check of 20 by the user and, in Step 6, the `data-auditor` subagent.

## Why / alternatives considered
- **A real tool for Claude** (an MCP server `claude -p` can call): Claude could check as it writes, but it's more moving parts for the same result, and the script still has to check the final output (ADR 0002).
- **Paid API tool runner (the original plan):** costs money per call; the user chose the subscription (ADR 0005).
- **Claude writes the pinyin:** code can't fully check it, while `pypinyin` + our dictionary gets it right or nearly right for free.
- **No retry (drop failures):** simpler, but band-1 words are hard to write with so few allowed words, so the 95% bar would likely be missed.

## Consequences
- ✅ Same proven pattern as `answer_writer`; no new kind of Claude call.
- ✅ Every committed sentence has passed the checker; the pinyin is free and repeatable.
- ⚠️ New dependencies: `jieba` (splits sentences into words) and `pypinyin`.
- ⚠️ `jieba` can split a sentence differently from how the HSK list writes a word, so the validator may reject good sentences. The allowed-word rules are tuned on the trial run.
- ⚠️ `pypinyin` shows tone changes the dictionary doesn't (`bú shì`). The user's call (M3): pronunciation is not a v1 concern.
