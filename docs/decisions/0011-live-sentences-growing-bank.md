# 0011: Example sentences are written live during the quiz and saved to a growing bank

- **Status:** Accepted (2026-11-04)
- **In plain words:** ADR 0008 planned a fixed set of sentences, written once before anyone studies. Instead, the quiz asks Claude for a fresh sentence while you play, checks it with the same scripts, shows it, and saves it to a **bank**. Each time a word comes up, a simple rule decides: a new sentence or one from the bank. The bank starts empty and grows as you play. This replaces ADR 0008's "one batch run before studying"; the write, check and retry pattern and its checks (ADR 0009, ADR 0010) stand.

## Context
- The 20-word trial (2026-11-04) worked, and the full batch run was next. The user said that isn't what they want: "I want the agent to just come up with new sentences … not necessarily the same for a single word every time", plus "banked sentences which we build up over time from the live generation".
- A fixed set of 2 sentences per word means you see the same sentences again and again.
- `claude -p` takes several seconds per call, so asking only when a question appears would make you wait.
- The judge (ADR 0007) already calls Claude during play, with a time limit, a safe fallback and an off switch (`--no-judge`). This uses the same pattern.

## Decision
1. **A live sentence per question.** In the sentence modes (`char_sentence`, `full`), the quiz asks Claude for one new sentence for the word. It uses the `sentence_writer` prompt and checks, for one word at a time: the sentence checker, the pinyin check and the English check. A sentence that fails is never shown.
2. **Asked ahead.** While you answer one question, the next question's sentence is being written, so there's usually no wait. A time limit (a setting) stops a slow call.
3. **The bank.** Every sentence that passes and is shown is saved to `data/generated/sentences.jsonl`, the same file and format as `sentence_writer`. It is committed, so new sentences can be reviewed in git and are never lost. The file grows, never shrinks, and holds at most a cap of sentences per word (a setting).
4. **New or banked: the rule.** For a word with `n` banked sentences, the chance of a new one is `max(floor, 1 / (1 + n))`, with `floor` = 0.2 to start. So 0 banked gives 100% (always new), 1 gives 50%, 3 gives 25%, and 4 or more gives 20%. A banked pick is the sentence you've seen **least recently**. When you saw each sentence is tracked in a small local file, gitignored like `progress.db`.
5. **Fallbacks.** If Claude is missing, slow, failing or out of usage, the quiz uses a banked sentence. If the bank has none for that word, the question is shown without a sentence and the quiz says so. After repeated failures the live part switches off for the rest of the quiz, as the judge does.
6. **Settings and off switch.** `--no-live` uses only the bank. The floor, the time limit and the cap are settings, to adjust after real play.
7. **No seed run.** The bank starts empty and grows from play (the user's choice). `sentence_writer`'s batch command stays as an optional way to top up the bank.

## Why / alternatives considered
- **A fixed batch set (ADR 0008):** instant and offline, but the same sentences every time, which is what the user didn't want.
- **Always live:** always new, but the bank never gets used, and every question needs Claude.
- **A coin flip between new and banked:** simpler, but a word with no banked sentences would often have nothing to show, and well-known words would keep paying for new sentences. The rule above fills each word's bank first, then mostly reuses it.
- **Seed the bank with a batch run first:** works offline from day one, but costs a full run (about 1.3 million tokens of plan usage) the user didn't want.

## Consequences
- ✅ New sentences as you play, a bank that grows by itself, and every shown sentence checked by scripts first.
- ✅ The quiz never gets stuck: bank fallback, time limit, automatic switch-off, `--no-live`.
- ⚠️ This changes the project rule "the quiz doesn't need Claude at runtime" (CLAUDE.md, PLAN.md): live sentences become a second optional runtime use, beside the judge.
- ⚠️ The sentence modes need Claude until the bank has sentences for a word. Offline with an empty bank, there's no sentence to show.
- ⚠️ Each new sentence is one call from your plan's usage. The prompt carries the whole allowed-word list, so even one word costs thousands of tokens. The trial's 20-word call was about 17,000 tokens. Measure a one-word call in the build, and shorten the prompt if needed.
- ⚠️ Playing changes a committed file; commit it now and then to keep the new sentences.
- Later (M5, `docs/FUTURE.md`): a banked sentence you got wrong comes back sooner.
