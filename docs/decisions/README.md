# Decision records (ADRs)

> **In plain words:** short notes that say *"we decided X, because Y"*. Code shows **what** was built. These notes show **why**, so nobody "fixes" something that was done on purpose.

**ADR** = Architecture Decision Record. One file per big decision, numbered in order. Never deleted: if a decision changes, write a new ADR and mark the old one **Superseded by 00XX**.

## All decisions
| # | Decision | Status |
|---|---|---|
| [0001](0001-hsk3-standard.md) | Use the HSK 3.0 word lists (bands 1–3) | Accepted (counts → 0004) |
| [0002](0002-script-vs-agent.md) | Script if code can check it; agent if it needs judgment | Accepted |
| [0003](0003-block-contract.md) | Every block = SPEC.md + code + tests | Accepted |
| [0004](0004-word-list-source.md) | 2026 HSK 3.0 syllabus from `complete-hsk-vocabulary`, pinned | Accepted |
| [0005](0005-answer-agent-and-judge.md) | Grading = answer list + Claude judge, both via `claude -p` (subscription) | Accepted (one list → 0006; judge → 0007) |
| [0006](0006-one-answer-list.md) | One answer list (`answers.jsonl`); `cedict_cleaner` retired | Accepted |
| [0007](0007-generic-claude-judge.md) | Generic Claude judge in `quizkit`, with rules for trusting it (forced shape, eval set, cache, safe failure) | Accepted |

## Template
```markdown
# 00XX: <decision title>

- **Status:** Proposed | Accepted (YYYY-MM-DD) | Superseded by 00YY
- **In plain words:** one or two sentences.

## Context
What problem or question made us decide?

## Decision
What we chose.

## Why / alternatives considered
Other options, and why we didn't pick them.

## Consequences
What gets easier. What it costs.
```
