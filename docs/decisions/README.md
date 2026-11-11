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
| [0008](0008-sentences-write-check-retry.md) | Sentences: Claude writes, a script checks, Claude retries; pinyin by script | Accepted (word splitting → 0009, pinyin → 0010, live + bank → 0011) |
| [0009](0009-validator-reads-without-jieba.md) | The sentence checker reads with our own word list, not `jieba` ("readable at the band") | Accepted |
| [0010](0010-claude-writes-pinyin-script-checks.md) | Sentence pinyin: Claude writes it, a script checks every syllable is a real reading | Accepted |
| [0011](0011-live-sentences-growing-bank.md) | Sentences written live in the quiz and saved to a growing bank; a rule picks new or banked | Accepted |
| [0012](0012-sentence-translation-mode.md) | Sentence translation modes (`translate`, `translate_pinyin`), graded for the gist by the Claude judge; self-marking without Claude | Accepted |
| [0013](0013-progress-and-leitner-boxes.md) | Progress saved per word and skill (SQLite); Leitner boxes (5, waits 0/1/3/7/21 days) decide which words come next; `hsk stats` | Accepted |
| [0014](0014-web-ui-streamlit-shared-setup.md) | A Streamlit web quiz (quiz + stats), on one shared HSK setup used by the terminal and the web; the engine takes your own mark after an answer | Accepted |
| [0015](0015-sentence-audits-act-without-a-human-gate.md) | Sentence audits act on their own: whatever the `data-auditor` flags (or is unsure about) is removed, with a dated report; nobody approves sentences | Accepted |

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
