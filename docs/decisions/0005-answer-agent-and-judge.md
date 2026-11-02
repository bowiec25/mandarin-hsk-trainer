# 0005: Answer list + Claude judge, run under the Claude subscription

- **Status:** Accepted (2026-11-02); partly superseded by [0006](0006-one-answer-list.md) (one answer list: the quiz no longer adds the `cedict_cleaner` answers)
- **In plain words:** grading gets two layers. **1. An answer list**: Claude writes, once and ahead of time, the English answers a learner might type for each word ("father, dad, papa"); a script checks the list and it's committed. **2. A Claude judge**: only when the list says "wrong", the quiz asks Claude "is this answer right?" and saves the verdict so it never asks twice. Both call Claude through `claude -p` (Claude Code run from a script), so they run under your subscription, not a paid API key.

## Context
- The M3 play-test showed the rule-based `cedict_cleaner` marks good answers wrong. Rules can't judge meaning (ADR 0002: that needs an agent).
- The planned sentence modes (`char_sentence`, `full`) still ask for the meaning of **the word**, so a fixed list works for them.
- A later idea, **translating a whole sentence**, has endless right answers. No fixed list can cover it: it needs a judge at quiz time.
- The user wants this to run under their Claude subscription.

## Decision
**Layer 1: answer list (offline batch agent, `answer_writer`)**
- A batch script sends the cards to Claude in chunks and writes `data/generated/answers.jsonl`: one line per card with its answers, plus the model and prompt version.
- **A validator script** checks it: every one of the 978 cards is there exactly once; 1–10 answers each; each is short, typeable English (letters, spaces, `'` and `-`); no duplicates.
- The quiz accepts **the agent's answers plus the `cedict_cleaner` answers**, so nothing the quiz accepts today is lost.
- The user spot-checks 20 cards, then it's committed. `--limit N` and `--dry-run` as usual.

**Layer 2: judge (at quiz time, only after the list says "wrong")**
- `quizkit` gets a generic "judge" slot (like the `cleaner` slot): any quiz can plug one in, or none. `quizkit` stays free of Mandarin and of Claude.
- The HSK judge asks Claude with the word, its answers and what you typed, and gets back a yes/no plus a short reason. A script checks that the reply has that shape.
- **Every verdict is saved** in `data/judge_cache.jsonl` (gitignored, like `progress.db`), so the same answer is never asked twice.
- The screen says when the judge decided ("✓ accepted by the Claude judge: 'papa' means father").
- **If Claude can't be reached** (no internet, timeout ~15 s), the answer stays wrong with a note "couldn't check"; the quiz never breaks. `--no-judge` turns it off.

**How both call Claude:** `claude -p ... --output-format json` (headless Claude Code), with no tools allowed. Checked 2026-11-02: it works here, takes about 8 s per call, and reports tokens per call, which we log. The `total_cost_usd` it prints is the list-price equivalent, not a charge on the subscription.

## Why / alternatives considered
- **List only (no judge):** cheap and offline, but can't do sentence translation later, and still misses answers nobody thought of.
- **Judge only (no list):** every answer would wait ~8 s for Claude and need internet. The list answers most instantly.
- **Paid API (`anthropic` SDK + key in `.env`):** faster per call and the usual way to build agents, but costs money per call and the user prefers the subscription. Can be swapped in later behind the same slot.
- **Claude writes the list in a chat session:** free, but can't be re-run and has no log (breaks ADR 0002 guardrail 4).

## Consequences
- ✅ Fixes the play-test problem; the judge is the piece that makes sentence translation possible later.
- ✅ No API key, no per-call bill.
- ⚠️ This refines ADR 0002: "agent = Claude API + tools" now includes `claude -p`. ADR 0002's one runtime exception (the grading fallback with a cache) moves from M5 into M4.
- ⚠️ The judge needs internet at the moments it's asked, and each first-time ask takes ~8 s.
- ⚠️ A judge verdict can't be checked by code (only its shape can), so it's shown on screen, saved, and can be reviewed. Folding good verdicts back into the answer list is a later idea (`docs/FUTURE.md`).
- ⚠️ Depends on the `claude` command being installed and logged in. Subscription limits apply, so big batches go in chunks.
