# Where we are

- [x] Plan agreed (2026-11-01)
- [x] **M0 Setup** (done 2026-11-01)
  - [x] 1. Install GitHub CLI + uv (gh 2.103.3, uv 0.13.6; `--version` verified 2026-11-01)
  - [x] 2. `gh auth login` + check git identity (GitHub: bowiec25; git: Cameron Bowie / noreply email)
  - [x] 3. `uv init --package` + `git init -b main` (branch renamed from `master`; hello runs)
  - [x] 4. Skeleton: .gitignore, README, CLAUDE.md, CI, PR template (+ .gitattributes, COURSE_MAP.md; first commit)
  - [x] 5. Create GitHub repo + first push (public: github.com/bowiec25/mandarin-hsk-trainer; CI green)
  - [x] 6. Protect `main` (PR + green `check` required, admins included; tested)
  - [x] 7. Delete old `Desktop\MandarinLearningTest` (was empty)
- [x] **M1 Foundations** (issue #3, done 2026-11-01)
  - [x] 1. GitHub issue #3 (checklist of the pieces)
  - [x] 2. ADRs 0001–0003 in `docs/decisions/` (first use of plan mode)
  - [x] 3. Data shapes: `BlockSpec` + pydantic `Card` / `Question` + `Mode` + `HSK_MODES` (16 tests; packages now `quizkit` + `hsk_trainer`, command `hsk`)
  - [x] 4. `.claude/settings.json` allowlist + hooks: `ruff format` after edits + a **PreToolUse hook that blocks any tool/command touching `.env`** (19 hook tests; live-tested)
  - [x] 5. `/new-block` skill (+ tested `quizkit.scaffold` script + `missing_spec_sections` checker)
  - [x] 6. Subagents: `block-reviewer` + `test-writer`, wired into `/new-block`, CLAUDE.md and the PR template (demo: both caught 2 planted mistakes; re-review ✅). `data-auditor` moved to M4
- [ ] **M2 Data in** (issue #10) ← *next: Step 3, scaffold improvement*
  - [x] 1. GitHub issue #10
  - [x] 2. Source chosen + pinned → ADR 0004 (**2026 revised syllabus**: 294 / 491 / 978 words; MIT; SHA `7ac65bf`)
  - [ ] 3. Scaffold: contract test also checks `BLOCK_SPEC` inputs/outputs (block-reviewer suggestion)
  - [ ] 4. `fetcher` block
  - [ ] 5. `normalizer` block → `cards.jsonl`
  - [ ] 6. Word-count test (exact counts + within 5% of 300 / 500 / 1,000)
- [ ] M3 First playable quiz
- [ ] M4 Sentences (first agent)
  - [ ] `data-auditor` subagent (moved from M1: needs real sentences to test against)
- [ ] M5 Learning smarts
- [ ] M6 Web UI

**Side topics (cover when relevant):**
- [ ] VS Code + Claude extension vs terminal: when to use which
- [ ] Managing Claude sessions (`/clear`, `/compact`, `--continue`/`--resume`, one session per task)
- [ ] Git worktrees for parallel Claude sessions (intro at M3, when two features can run side by side)

---

# Plan: Mandarin HSK 3.0 (Bands 1–3) Trainer, built as reusable blocks

## Context
You want a vocab tester for HSK 3.0 (**updated 2026-11-02: the 2026 revised syllabus**, cumulative ~300 / 500 / 1,000 words for bands 1–3; see ADR 0004) with four question modes:

| Mode | Shown | You type |
|---|---|---|
| `char` | 汉字 | English |
| `char_pinyin` | 汉字 + pinyin | English |
| `char_sentence` | 汉字 + sentence in 汉字 | English (meaning of the word) |
| `full` | 汉字 + pinyin + sentence in 汉字 + sentence pinyin | English |

The app is half the goal. The other half is learning to build it properly: a GitHub workflow, Claude Code best practice, and well-specified building blocks (scripts and agents) that you can reuse for other testing tools. You manage the build and I walk you through every step.

**Environment facts:** the project currently sits inside your `Desktop` git repo, so it moves to `C:\Users\Lenovo\code\mandarin-hsk-trainer`. Python 3.13 and git are installed. `gh` (GitHub CLI) and `uv` (Python project manager) are not, so we install both.

---

## 1. Core design principle: script vs agent (gets its own decision record, ADR-0002)

**Rule: if code can check that the output is right, write a script. If the task needs language judgment, use an agent, and have a script validate whatever the agent produces.**

| Use a **script** when… | Use an **agent** (Claude API + tools) when… |
|---|---|
| The steps are known and repeatable | The task is open-ended or needs language skill |
| Correctness can be checked in code | Quality needs judgment (natural sentences, synonyms) |
| It runs often or must be free and instant | It runs rarely (a batch job) and its output gets cached |
| Example: download a file, parse it, run the quiz | Example: write a sentence using only HSK-1 words |

Guardrails for every agent:
- Agents run **offline as batch jobs**. They write files to `data/generated/` that get reviewed and committed, so the quiz never needs the API at runtime (except an optional grading fallback).
- Every agent output goes through a **script validator** before it is accepted.
- Agent tools are **script functions**: the agent calls deterministic code (e.g. `check_vocab_level`) instead of guessing.
- Every agent has `--limit N` and `--dry-run` flags, and logs the model, prompt version and token cost.

## 2. Building blocks

Every block follows one **contract**: a folder holding `SPEC.md` (Goal, Kind, Inputs, Outputs, Tools, Failure modes, How to test), the code, and tests. Inputs and outputs are typed with pydantic. This contract is what makes blocks reusable.

| # | Block | Kind | Goal | Output |
|---|---|---|---|---|
| 1 | `fetcher` | script | Download the HSK 3.0 word list from a pinned source URL, verify the checksum, store the raw file | `data/raw/` |
| 2 | `normalizer` | script | Convert the raw list to `Card` records (id, hanzi, pinyin, meanings[], band, part of speech) | `data/processed/cards.jsonl` |
| 3 | `sentence_writer` | **agent** | For each word, write 1–2 short, natural sentences that use only words at or below its band, with pinyin and English | `data/generated/sentences.jsonl` |
| 4 | `sentence_validator` | script | Independently check the sentences: target word present, vocab within band (segmented with jieba), pinyin matches pypinyin, length limits | pass/reject report |
| 5 | `deck_builder` | script | Combine cards, sentences and a mode into a list of questions | in memory |
| 6 | `grader` | script, with optional **agent** fallback | Normalize the answer and match it against meanings, synonyms and fuzzy matches (rapidfuzz). On a miss, it can optionally ask Claude "is this acceptable?" and cache the verdict to `accepted_answers.json` | correct / incorrect + feedback |
| 7 | `progress_store` | script | Log attempts in SQLite, then add spaced repetition (Leitner boxes) later | `data/progress.db` (gitignored) |
| 8 | `cli` | script | `hsk fetch`, `hsk build`, `hsk quiz --band 1 --mode char`, `hsk stats` (built with Typer) | terminal |

**Reusability split:** generic parts live in `src/quizkit/` (block contract, Card/Question models, modes, quiz engine, grader, progress store). Mandarin-specific parts live in `src/hsk_trainer/` (HSK source, pinyin, the sentence agent's prompt). A future "Spanish verbs tester" or "finance terms tester" reuses `quizkit` and writes only a new fetcher and normalizer.

Modes are **declared as config**, not hard-coded:
`MODES = {"char": ["hanzi"], "char_pinyin": ["hanzi","pinyin"], "char_sentence": ["hanzi","sentence"], "full": ["hanzi","pinyin","sentence","sentence_pinyin"]}`

## 3. Claude Code best-practice layer (the build tooling)

- **`CLAUDE.md`**: project rules (block contract, script-vs-agent rule, commands, "never commit .env", branch/PR workflow). Kept short, updated each milestone.
- **`.claude/settings.json`**: a permission allowlist (uv, pytest, ruff, git, gh) committed so the setup is reproducible.
- **`.claude/skills/new-block/`**: a `/new-block` skill that scaffolds a new block (SPEC.md template, module, test stub). This is the main reuse lever.
- **`.claude/agents/`**: build-time subagents with narrow goals, tools and instructions:
  - `block-reviewer`: checks that a block meets its SPEC and contract (read-only tools)
  - `test-writer`: writes pytest cases from a SPEC.md
  - `data-auditor`: spot-checks generated sentences and flags unnatural ones (read-only)
- **Hook** (optional, M1): run `ruff format` automatically after edits.
- **Workflow per milestone:** GitHub issue → plan mode → feature branch → small commits → PR → CI green → `/code-review` → merge. You approve each PR.
- **Runtime agents** use the Anthropic Python SDK's tool runner, with the model set in config (cheaper model for grading, stronger model for sentences). `ANTHROPIC_API_KEY` lives in `.env`, which is gitignored, and `.env.example` is committed.

## 4. Repo layout
```
mandarin-hsk-trainer/
├─ CLAUDE.md  README.md  pyproject.toml  uv.lock  .gitignore  .env.example
├─ .github/  workflows/ci.yml (ruff + pytest)  pull_request_template.md  ISSUE_TEMPLATE/
├─ .claude/  settings.json  agents/*.md  skills/new-block/
├─ docs/decisions/  0001-hsk3-standard.md  0002-script-vs-agent.md  0003-block-contract.md
├─ src/quizkit/          # generic, reusable
│   ├─ blocks/base.py    # BlockSpec + run contract
│   ├─ models.py  modes.py  engine.py  grader.py  progress.py
├─ src/hsk_trainer/      # Mandarin-specific
│   ├─ blocks/fetcher/  normalizer/  sentence_writer/  sentence_validator/   (each: SPEC.md + code)
│   ├─ cli.py
├─ data/  raw/  processed/  generated/   (committed; progress.db ignored)
└─ tests/
```

## 5. Milestones (each one = GitHub issue + branch + PR; I walk you through each)

**M0: Setup (together, step by step)**
1. `winget install GitHub.cli` and `winget install astral-sh.uv`, then reopen the terminal
2. `gh auth login` (you run it with `! gh auth login` because it's interactive) and check `git config user.name/email`
3. `mkdir C:\Users\Lenovo\code\mandarin-hsk-trainer`, then `uv init --package`, `git init -b main`
4. Add the skeleton: .gitignore, README, CLAUDE.md (via `/init`, then edit), CI workflow, PR template
5. `gh repo create mandarin-hsk-trainer --private --source . --push`
6. Protect `main`: require a PR and a passing CI run before merging
7. Delete the empty `Desktop\MandarinLearningTest` folder

**M1: Foundations.** ADRs 0001–0003, the `BlockSpec` base and pydantic models, the `/new-block` skill, the three build subagents, `.claude/settings.json`.

**M2: Data in.** `fetcher` + `normalizer` (scaffolded with `/new-block`). First step: choose and pin the HSK 3.0 source (candidate: the open `complete-hsk-vocabulary` dataset on GitHub, checking its licence first), then commit `cards.jsonl`. Tests check word counts per band.

**M3: First playable quiz.** `deck_builder`, the script `grader`, `engine`, CLI with modes `char` and `char_pinyin`. You can start studying here.

**M4: Sentences (first agent).** The `sentence_writer` agent with a `check_vocab_level` tool, plus `sentence_validator`. Trial run on 20 band-1 words → you review → full batch (I show the estimated cost first) → commit. This unlocks modes `char_sentence` and `full`.

**M5: Learning smarts.** `progress_store`, Leitner spaced repetition, `hsk stats`, the optional agent grading fallback with cached verdicts.

**M6: Web UI.** A Streamlit front end on the same `quizkit` engine, with no logic duplicated.

## 6. Verification
- Every PR: `uv run ruff check`, `uv run pytest`, and green CI on GitHub
- M2: band word counts match the official totals (±known duplicates)
- M3: `uv run hsk quiz --band 1 --mode char --n 10` plays end to end, and the grader accepts "to love" or "love" for 爱
- M4: the validator passes ≥95% of generated sentences, and the `data-auditor` subagent plus your own spot-check of 20 samples
- Reuse check (end of M3): scaffold a toy second deck (e.g. 10 country capitals) using only `quizkit` + `/new-block`, to prove the blocks are generic

## How we'll work (this is your first fully specified project)
- **Small steps with a stop after each one.** Every step has four parts: **What** we're doing, **Why** it's best practice, the **Claude Code feature** involved, and **Checkpoint** (what you should now see). Then I stop and wait for your go-ahead.
- **Tied to your course.** Where a step uses something from *Claude Code in Action* (CLAUDE.md and context, plan mode, custom commands and skills, subagents, hooks, MCP, the GitHub integration, the SDK), I name it so you can link the step to the lesson.
- **You run the interactive commands** (logins, installs) with `! <command>` so the output lands in our chat. I do the file edits and explain each one.
- **You stay the manager:** you open the issues, approve the plans and merge the PRs.
- A running **"Where we are"** checklist at the top of `docs/PLAN.md` gets ticked off as we go, so we can always see our progress.

## First actions once approved (then STOP)
1. Create `C:\Users\Lenovo\code\mandarin-hsk-trainer\docs\`
2. Save this plan there as `docs/PLAN.md`, with a "Where we are" checklist (M0 step 1 = next) added at the top
3. Save a memory note about how you like to work (step-by-step, explained, stop often)
4. Stop and explain M0 Step 1 (installing `gh` and `uv`: what they are and why we use them) before anything gets run
