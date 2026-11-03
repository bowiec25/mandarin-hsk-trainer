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
- [x] **M2 Data in** (issue #10, done 2026-11-02)
  - [x] 1. GitHub issue #10
  - [x] 2. Source chosen + pinned → ADR 0004 (**2026 revised syllabus**: 294 / 491 / 978 words; MIT; SHA `7ac65bf`)
  - [x] 3. Scaffold: contract test also checks `BLOCK_SPEC` inputs/outputs (block-reviewer suggestion; drift test caught a planted mismatch)
  - [x] 4. `fetcher` block + generic `quizkit.download` helper (3 review rounds → ✅; raw data in `data/raw/hsk3_2026/`)
  - [x] 5. `normalizer` block → `cards.jsonl` (978 cards: 294 / 197 / 487; 3 review rounds → ✅; shared `quizkit.files.write_atomically`)
  - [x] 6. Word-count test (exact counts + within 5% of 300 / 500 / 1,000, + `cards.jsonl` up to date; 2 planted mistakes caught)
- [x] **M3 First playable quiz** (issue #16, done 2026-11-02)
  - [x] 1. Issue #16 + "Still the right thing?" check + housekeeping (build map saved as `docs/build-map/index.html`; CLAUDE.md rule to update it after each step). Decisions: `--band 2` = only the band-2 words; the grader forgives small typos, not wrong words
  - [x] 1b. Build map: new "What we've built, by kind" section (incl. subagent vs agent), "journey of one change" (every hook, skill, subagent and gate; code review shown as a gap), frozen snapshots per step in `docs/build-map/snapshots/`
  - [x] 1b+. Build map: "Flow diagrams: three views" (how a step is built, in lanes; what the app does; one Claude action up close)
  - [x] 1c. Code review (PR #18 + this step's PR): `/code-review` before every PR + Claude GitHub app (`/install-github-app`, subscription token; ⚠️ the token was made 2026-11-02 and expires after 1 year, so **renew it before 2027-10-15**)
  - [x] 1d. Proved the GitHub review with a planted-bug test PR (#20, closed, not merged): caught ×10-instead-of-×100, missed divide-by-zero. Workflow left as installed (it works on code PRs)
  - [x] 2. Grading, as 2 blocks (the clutter scan showed most clutter is dictionary-specific): **2a `grader`** (generic, `quizkit`: case, punctuation, leading to/a/an/the, typos 0/1/2 by length via rapidfuzz OSA; a quiz passes its own `cleaner`) + **2b `cedict_cleaner`** (`hsk_trainer`: 8 rules, every one of the 978 cards keeps an answer; a stopgap until the M4 answer agent). The real-data test caught a grader bug (给 = "to" was dropped)
  - [x] 3. `deck_builder` block (generic, `quizkit`): `build_deck(cards, mode, n, levels, seed)`; `levels` is a list so "bands together" is free later; its own block so M5 can make "what's next" smart. Built **in parallel with the engine** using a git worktree (first worktree demo). Future ideas now live in `docs/FUTURE.md`
  - [x] 4. `engine` block (generic, `quizkit`, PR #24), in two layers: `QuizSession` (the brain, no screen code, so the M6 web UI can reuse it) + `run_quiz(questions, ask, tell, cleaner, settings)` (the loop; `ask` returning `None` = quit). Built in a **parallel worktree session**; merged `main` in first, no conflicts
  - [x] 5. CLI (Typer, PR #26): `hsk quiz --band N --mode char|char_pinyin --n N [--seed S]`. Not a block (the shell around them). Ctrl-C / end-of-input quits and keeps the score; "Only 197 band-2 words"; sentence modes refused until M4; UTF-8 output for Windows pipes. Tested with scripted keystrokes (31 tests); `/code-review`: 8 findings, 6 fixed
  - [x] 6. Play-test (works; the user's verdict: grading needs judgment, not rules → M4 answer agent) + reuse check (`examples/capitals_quiz.py` plays with `hsk_trainer` blocked; `tests/test_reuse.py` also scans that no `quizkit` file imports `hsk_trainer`). The check found a weak spot, so the **engine** now treats Ctrl-C anywhere in `run_quiz` as a quit (full block routine) and the CLI uses `run_quiz` again. Plus the M3 lessons in the playbook
- [ ] **M4 Sentences (first agent)** ← *now* (issue #28)
  - [x] 1. Stronger "Still the right thing?" (user's ask: don't stay wedded to the original plan): required field in a GitHub **issue form**, a section in the **PR template**, and a **CI check** that fails a PR with that section empty (`.github/scripts/check_pr_body.py`, 22 tests). It runs inside the required `check` job, so protected `main` enforces it. Re-check of M4: the answer agent now comes **before** `sentence_writer` (it fixes the play-test problem and is a smaller first agent)
  - [x] 2. **ADR 0005**: grading = two layers. (1) an **answer list** written once by an offline batch agent, checked by a script, spot-checked, committed; (2) a **Claude judge** asked only when the list says "wrong", verdicts cached. Both call Claude via `claude -p` (**subscription**, no API key; tested: ~8 s a call, reports tokens). Still-the-right-thing change: the user spotted that sentence translation can't use a fixed list, so the judge (planned for M5) moves into M4
  - [x] 3. `answer_writer` agent + validator → `data/generated/answers.jsonl` (all 978; 25 `claude -p` calls, ~148k tokens; the checker caught 9, re-runs fixed them; trial of 20 + random spot-check of 20 approved: "a bit generous is fine"). Shared `quizkit.claude.ask_claude` helper (no tools, empty folder). 2 block-reviewer rounds → ✅. The quiz plugs the file in at Step 4
  - [x] 4a. **One answer list** (issue #33, ADR 0006 = PR #34, code = PR #35; changed from ADR 0005 after measuring: the old cleaner list added 1,434 mostly-junk answers like 猫 "modem"). The quiz reads only `answers.jsonl`, through `answer_writer.load_answers` (same checker as the writer, one band at a time); `cedict_cleaner` and the `cleaner` slot deleted, and `tests/test_retired.py` keeps them gone; the writer never shrinks the file. 3 block-reviews ✅, 2 `/code-review` passes (18 findings, 13 fixed). The `meanings` rename moved to `docs/FUTURE.md` (keep the step simple)
  - [x] 4b. **Generic Claude judge** (issue #37, ADR 0007 = PR #38, code = PR #39; changed from ADR 0005: the user will reuse it in other quizzes, so it's one generic `quizkit.blocks.judge` block, not an HSK judge). Asked only when the list says wrong; reply forced with `--json-schema` + checked; verdicts cached (keyed by what Claude saw); 2 failures in a row switch it off; `--no-judge`. Eval: 31 hand-labelled cases, Haiku passes (no wrong "yes"), 4 borderline answers labelled reject by choice. 540 tests. Lesson: this PR did four jobs; split agent work next time
  - [ ] 5. `sentence_writer` + `sentence_validator` (unlocks `char_sentence`, `full`)
  - [ ] 6. `data-auditor` subagent (moved from M1: needs real sentences to test against)
- [ ] M5 Learning smarts
- [ ] M6 Web UI

**Future (not v1):** moved to its own list, **`docs/FUTURE.md`** (smart "what's next" deck, mistake log, sentence translation, bands together, listening). Add new ideas there.

**Side topics (cover when relevant):**
- [ ] VS Code + Claude extension vs terminal: when to use which
- [x] Managing Claude sessions (`/clear`, `/compact`, `--continue`/`--resume`, one session per task) (covered at the 2026-11-02 break)
- [x] Git worktrees for parallel Claude sessions (M3 Steps 3–4: deck_builder here, engine in a second session in `../mandarin-hsk-trainer-engine`)

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
| 4 | `sentence_validator` | script | Independently check the sentences: target word present, vocab readable at the band (our own word list, ADR 0009), pinyin matches pypinyin, length limits | pass/reject report |
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

**M5: Learning smarts.** `progress_store`, Leitner spaced repetition, `hsk stats`. (The agent grading fallback moved to M4, ADR 0005.)

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
