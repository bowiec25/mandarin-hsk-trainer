# 0002: Script vs agent

- **Status:** Accepted (2026-11-01)
- **In plain words:** if code can **check** that the answer is right, write a normal **script**. If the job needs **language judgment** (like writing a natural sentence), use an **AI agent**, and a script always checks what the agent made.

## Context
Some jobs in this project are mechanical (download a file, run the quiz), and some need language skill (write example sentences using only easy words). AI can do both, but AI is slower, costs money, and can be wrong in ways that are hard to spot. We need a clear rule for which tool to use.

## Decision
| Use a **script** when… | Use an **agent** (Claude API + tools) when… |
|---|---|
| The steps are known and repeatable | The task is open-ended or needs language skill |
| Correctness can be checked in code | Quality needs judgment (natural sentences, synonyms) |
| It runs often or must be free and instant | It runs rarely (a batch job) and the output is saved |
| e.g. download, parse, run the quiz | e.g. write a sentence using only HSK-1 words |

**Guardrails for every agent:**
1. **Offline batch jobs only.** Agents write files to `data/generated/`, which get reviewed and committed. The quiz never needs the API to run (the one exception is the optional grading fallback, whose answers are saved to a cache).
2. **A script validator checks every agent output** before it's accepted.
3. **Agent tools are script functions.** The agent calls deterministic code (e.g. `check_vocab_level`) instead of guessing.
4. **Every agent has `--limit N` and `--dry-run`**, and logs the model, the prompt version and the token cost.

## Why / alternatives considered
- **All scripts:** can't write natural sentences or judge "is *adore* an OK answer for 爱?".
- **All agents:** slow, costs money on every quiz, results change from run to run, and it's hard to test.
- **Agent with no checking:** quietly lets bad sentences in (e.g. words above the band).

## Consequences
- ✅ The quiz is free, instant, and works offline.
- ✅ Agent mistakes get caught by code, not by luck.
- ✅ Costs are visible and capped (`--limit`, `--dry-run`, logged tokens).
- ⚠️ Each agent needs a matching validator script, which is extra work, but it's the point.
