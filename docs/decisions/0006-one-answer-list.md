# 0006: One answer list

- **Status:** Accepted (2026-11-03)
- **In plain words:** the quiz checks your answer against **one** list: the answers Claude wrote, in `data/generated/answers.jsonl`. The old rule-based list (the dictionary text tidied by `cedict_cleaner`) is retired. This replaces one bullet of ADR 0005 ("the quiz accepts the agent's answers plus the `cedict_cleaner` answers"); the rest of ADR 0005 still stands.

## Context
ADR 0005 kept both lists "so nothing the quiz accepts today is lost". Nobody measured what the old list added. Before building it (M4 Step 4a, 2026-11-03) we did:
- **The old list adds 1,434 answers on 456 of the 978 words**, and most are senses an HSK learner isn't taught, which Claude left out on purpose: 猫 cat → "modem", 二 two → "stupid", 东方 east → "two-character surname Dongfang", 块 piece → "soap", "cake". Keeping them marks wrong answers right and shows junk after a miss.
- **Joining the lists is fiddly:** Claude's answers can't go through the cleaner (it would damage 21 of them: 姓 "surname" → nothing, "classifier for books" → "books"), so the quiz would need two paths for two lists.
- Two lists also make a verdict hard to trace: "why did this count?" could have either answer.

## Decision
- **The quiz grades against `answers.jsonl` only.** If the file is missing, the quiz stops with a clear message (it is committed, so this means a broken checkout).
- **`cedict_cleaner` is deleted**, with its tests. It was always a stopgap (M3 Step 2).
- **The grader's and engine's `cleaner` slot is removed**: nothing plugs into it any more. The judge (M4 Step 4b) gets its own slot.
- **The dictionary text stays in `cards.jsonl`, named `meanings`**, not `answers`: it is the answer writer's hint, not what the quiz accepts.
- **Answers the list misses go to the judge** (ADR 0005, layer 2).

## Why / alternatives considered
- **Both lists (ADR 0005 as written):** loses nothing, but accepts the junk above, needs two grading paths, and is harder to trace.
- **Both lists, but filter the old one:** more rules to keep up, for the few good answers the old list has that Claude's lacks. The judge covers those, and its verdicts can be folded into the list later (`docs/FUTURE.md`).
- **One list (chosen):** one place to look, one path, and every accepted answer says which model and prompt version wrote it.

## Consequences
- ✅ Simpler and traceable: one file decides what counts.
- ✅ Fewer wrong answers marked right.
- ⚠️ A few good answers only the old list had now count as wrong until the judge (Step 4b) is in, or until the answer list is improved.
- ⚠️ The quiz depends on `answers.jsonl` being complete, so the answer writer must never drop lines it hasn't replaced (fixed in the same step).
- 📝 Lesson: before keeping a fallback "so nothing is lost", measure what it actually adds.
