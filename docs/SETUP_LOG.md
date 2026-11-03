# Setup Log: what we did, and why

A plain-English record of each setup step: **what** it does, **why** it's best practice, and anything worth remembering.
New entries go at the bottom as we go. Each one starts with a short **In plain words** box. The details come after.

---

## 🟢 Quick summary (simple English)

| Step | What we did | Why |
|---|---|---|
| 1 | Installed `gh` (talks to GitHub) and `uv` (manages Python) | The tools we need |
| 2 | Logged this PC in to GitHub, and set the name stamped on your work | So uploads work without passwords, and work is credited to you |
| 3 | Made the folder a Python project, and started a change history | So the code has a home, and every change can be undone |
| 4 | Added safety files: hide secrets, checks, a briefing note for Claude, a README | So mistakes and leaks get caught early |
| 5 | Uploaded to GitHub (public) | Backup, and GitHub re-runs the checks on a fresh computer |

**The checks are scripts, not AI agents.** They simply pass or fail:
- `ruff check`: looks for sloppy or buggy code (like a spell-checker)
- `ruff format`: checks the layout is tidy (like auto-formatting in Word)
- `pytest`: runs our tests (a checklist: "does the app load?")

**What happens on every upload (CI):** GitHub reads `ci.yml` (our to-do list), takes a fresh computer, installs the project and runs the checks. ✅ = safe, ❌ = something's wrong.
**Why bother?** It proves the code works on *any* computer, not just yours.

---

## Key idea: `git` vs `gh`

| | `git` | `gh` (GitHub CLI) |
|---|---|---|
| What it is | The version-control tool itself | A helper for the GitHub *website* |
| Works on | Your local folder and its history | Your GitHub account online |
| Needs internet / GitHub? | No, it works fully offline | Yes |
| Typical jobs | `init`, `add`, `commit`, `branch`, `push` | create repos, log in, open PRs and issues, check CI |
| Made by | Open-source (Linus Torvalds, 2005) | GitHub |

**Rule of thumb:** `git` manages your code's history. `gh` manages things that only exist on github.com.
Git also works with GitLab, Bitbucket or no remote at all. GitHub is just one place to store a git repo.

---

## M0 Step 1: Install `gh` and `uv` (2026-11-01)

**What:** installed two command-line tools with `winget` (Windows' package manager).
- `gh` 2.103.3: talks to GitHub from the terminal (repos, PRs, issues, CI status).
- `uv` 0.13.6: a fast all-in-one Python manager (Python versions, virtual environments, dependencies, lock file).

**Why it's best practice:**
- With `winget`, installs are one command, repeatable, and easy to update (`winget upgrade`).
- `gh` lets you, and Claude, do GitHub work without clicking around the website, so it's scriptable and fits the terminal workflow.
- `uv` replaces `pip` + `venv` + `pip-tools` + `pyenv` with a single tool, and it is far faster. It's the current modern standard.

**Checked by:** `gh --version` and `uv --version` in a fresh terminal (a new terminal is needed so it picks up the updated PATH).

---

## M0 Step 2: Log in to GitHub + set git identity (2026-11-01)

**What:**
1. `gh auth login`: your PC got a **token** (a revocable key card) for GitHub account `bowiec25`, stored in Windows Credential Manager. Git was set up to use it for HTTPS pushes.
2. `git config --global user.name / user.email`: every commit you make is stamped "Cameron Bowie <221522165+bowiec25@users.noreply.github.com>".

**Note:** this set up the **computer**, not this project. `--global` = all projects on this PC. The folder only connects to GitHub in Step 5.

**Why it's best practice:**
- **No passwords:** the token is stored securely and can be revoked at any time (GitHub → Settings → Applications).
- **Set up once:** every future project on this PC can use it.
- **Privacy:** the noreply email keeps your Gmail out of public commit history, and commits still link to your profile.
- **Credit:** commits show up as yours on GitHub.

**Checked by:** `gh auth status` and `git config --global --list`.

---

## M0 Step 3: Make the folder a Python project + git repo (2026-11-01)

**What:**
- `uv init --package` creates `pyproject.toml` (the project's ID card: name, Python version, dependencies, commands), `src/mandarin_hsk_trainer/` (the code), `.python-version` (pins Python 3.13) and `README.md`.
- `git init -b main` creates a hidden `.git/` folder: a local history notebook, starting on a branch called `main`.

**Why `git init` and not `gh`?** Starting a history is a *local* job, and no GitHub is needed. `gh` only joins in at Step 5, when we create the online copy.

**Why it's best practice:**
- `pyproject.toml` is the single modern home for project settings (it replaces `setup.py` + `requirements.txt`).
- `--package` = **src layout**: tests run against the installed code, not loose files, which is the standard for reusable code (our future `quizkit`).
- uv's lock file (`uv.lock`) gives everyone (you, CI, future-you) identical library versions.
- Start git *before* writing code, so every change can be undone, compared and reviewed.

**What actually happened:**
- `uv init` **ran `git init` itself**, so it named the branch `master` (git's old default) and our `git init -b main` was ignored. Because there were no commits yet, we renamed it with `git symbolic-ref HEAD refs/heads/main`.
- uv also created a `.gitignore` (it ignores `.venv/`, `__pycache__/`, build output). We'll extend it in Step 4.
- The first `uv run` created `.venv/` (the project's private sandbox, Python 3.13.7) and `uv.lock` (exact versions; commit this).
- uv put your git name and email into `pyproject.toml` as the author.

**Lesson:** always check what a tool did, and don't assume. `git branch --show-current` caught the problem.
Optional fix for every future project: `git config --global init.defaultBranch main`.

**Checked by:** `git branch --show-current` → `main`. `uv run mandarin-hsk-trainer` → `Hello from mandarin-hsk-trainer!`

---

## M0 Step 4: Skeleton files (2026-11-01)

**Scope note:** everything in Step 4 lives *inside this project folder*. Nothing global (`~/.claude`, other projects such as the financial modelling work) is touched.

### 4a. Keep secrets out
- `.gitignore` now also skips `.env`, `data/progress.db`, tool caches, editor folders and personal Claude files (`.claude/settings.local.json`, `CLAUDE.local.md`).
- `.env.example` is committed. It lists the keys needed (`ANTHROPIC_API_KEY=`) with no values. You copy it to `.env` and fill it in locally.
- `.claude/settings.json` has a **deny rule** `Read(./.env)`, so Claude Code can't open the secrets file in this project.

**Why:** leaked keys on GitHub get abused within minutes. The deny rule is a second lock: even Claude can't see the secret. Because `settings.json` is committed, everyone who clones the repo gets the same safety rule. (`settings.local.json` = your personal, uncommitted overrides.)

### 4b. Dev tools + smoke test
- `uv add --dev ruff pytest` adds **ruff 0.17.3** (linter and formatter) and **pytest 9.2.0** (tests) as *dev* dependencies: needed to build, not to use.
- `tests/test_smoke.py` checks that the package imports.

**Why:** gives Claude a **verification loop**. After each change I run `ruff check` + `pytest` and fix problems myself before you see them. It also gives CI something real to run on day one.

### 4c. GitHub plumbing
- `.github/workflows/ci.yml` runs on GitHub (Ubuntu) for every push to `main` and every PR. Steps: install uv → `uv sync --locked` (exact versions) → ruff check → ruff format check → pytest.
- Action versions were looked up live (`actions/checkout@v7`, `astral-sh/setup-uv@v10`) instead of guessed.
- `.github/pull_request_template.md` gives every PR a What / Why / How tested / Checklist form.

**Why:** CI is the neutral referee. "Works on my machine" isn't enough, so it has to pass on a clean server too. `--locked` fails if `uv.lock` is out of date, which catches forgotten lock updates.

**Checked by:** `uv run ruff check` → All checks passed. `ruff format --check` → 5 files formatted. `pytest` → 1 passed. `git status` does not list `.venv/` (ignored ✓).

### 4d. `CLAUDE.md` via `/init`
- You ran `/init`. Claude scanned the repo and wrote `CLAUDE.md` with: the commands (including how to run one test), the target architecture (`quizkit` generic vs `hsk_trainer` specific), the script-vs-agent rule, and the workflow rules.
- It's kept to about 35 lines on purpose.

**Why:** `CLAUDE.md` is loaded into **every** Claude session in this folder, so a fresh session already knows the rules and you don't have to re-explain. It's committed, so it's shared. Short matters: every line costs context in every session, and long files get skimmed. Edit it any time with `/memory` or directly. Personal-only notes go in `CLAUDE.local.md` (gitignored).

### 4e. README + `.gitattributes` + first commit
- `README.md` is for **humans** (what it is, how to install and run, how to develop). `CLAUDE.md` is for **Claude** (rules and commands). Different readers, different files.
- `.gitattributes` with `* text=auto eol=lf`: Windows ends lines with CRLF, Linux (CI) with LF. This stores everything as LF in git and removed the `LF will be replaced by CRLF` warnings. It applies to this repo only.
- Before committing, we checked the staged list with `git status` and confirmed that no `.env`, `.venv/` or `progress.db` was included.

**Permission rule vs hook (asked during this step):** `deny: Read(./.env)` is a *permission rule*, a fixed allow/ask/deny line in `settings.json`. A *hook* is a script that runs automatically at set moments (e.g. after every edit). Rules are guardrails, not a vault. A hook can add a stricter second lock (planned for M1).

---

## M0 Step 5: Create GitHub repo + first push (2026-11-01)

> **In plain words:** we uploaded the code to GitHub. GitHub then ran the checks on a fresh computer. The first try failed because a tool version name was wrong (my mistake). I read the error, fixed it, uploaded again, and it passed ✅.

**What:** `gh repo create mandarin-hsk-trainer --public --source . --remote origin --push`
- This created https://github.com/bowiec25/mandarin-hsk-trainer, linked the folder to it under the nickname `origin`, and uploaded the commits.
- After that, `git push` / `git pull` sync with GitHub.

**Public vs private:** we chose **public**, because on GitHub's free plan branch protection (Step 6) only works on public repos. Before pushing, we scanned what would be visible: no Gmail (noreply email), no secrets; only the name "Cameron Bowie" and username. GitHub push protection (it blocks pushes containing API keys) is on automatically for public repos.

**Two failures, both useful lessons:**
1. **Push rejected: missing `workflow` scope.** GitHub treats CI files as extra-sensitive (they run code on its servers), so the token needs explicit permission. Fixed with `gh auth refresh -h github.com -s workflow`. Principle: sensitive things need explicit permission.
2. **First CI run failed in 3s: `Unable to resolve action astral-sh/setup-uv@v10`.** That project only publishes exact tags (`v10.3.3`), not a moving `v10`. Fixed by pinning the **commit SHA** with a version comment. Pinning third-party actions to a SHA is security best practice: a tag can be moved to different code, a SHA can't. (Official `actions/*` are lower risk, so a major tag is OK there.)

**Lesson:** I had checked that "v10 is the latest release" but not that the `v10` *tag* existed. Verify the exact thing you depend on. Reading the CI log (`gh run view <id> --log-failed`) gave the answer straight away.

**Why it's best practice:** off-site backup; CI proves the checks pass on a clean Linux machine; doing it with `gh` is repeatable and lets Claude drive GitHub.

---

## M0 Step 6: Protect `main` (2026-11-01)

> **In plain words:** GitHub now refuses any change to `main` unless it comes through a PR **and** the checks pass ✅. That applies to everyone, including you and Claude.

**What (the 4 rules):**
| Rule | Meaning |
|---|---|
| Require a PR | Changes go on a side branch first, then get proposed |
| Require the `check` CI job to pass | Can't merge if CI is ❌ (and the branch must be up to date with `main`) |
| No force-push | Nobody can overwrite history |
| No deleting `main` | It can't be removed by accident |

Also: **applies to admins too** (that's you). Required approvals = **0**, because GitHub doesn't let you approve your own PR. You still review it before merging.

**Why:** `main` = the version that always works. PRs give a review moment. Mistakes (including Claude's) can't slip in.

**How:** one `gh api -X PUT …/branches/main/protection` command (free because the repo is public).
**Tested by:** deliberately pushing straight to `main` → GitHub rejected it ✅. Then this log went in through PR #1.

### 6b. Merge settings + status line (2026-11-01)

> **In plain words:** GitHub now only offers **"Squash and merge"**, which turns each PR into one tidy commit, and it **deletes the side branch automatically** after merging. Separately, Claude Code now shows your **current branch** under the prompt box.

- **Merge settings** (repo setting via `gh api -X PATCH`, no PR needed): squash only; the commit uses the PR title + description; auto-delete the branch on merge.
  - *Why:* PR #1 was merged with a regular "Merge", which added an extra "Merge pull request #1" commit, and its branch was left behind on GitHub. Now neither can happen.
- **Status line** (`/statusline`, set up by a subagent): shows `folder [branch: …] model`.
  - **This project only:** it lives in `.claude/settings.local.json` + `.claude/statusline.ps1`, both gitignored (personal settings). Other projects keep the global status line.
  - *Why:* you always know which branch you're editing on.

---

## M0 Step 7: Delete the old Desktop folder (2026-11-01)

> **In plain words:** removed the empty `Desktop\MandarinLearningTest` folder (our first attempt at a project home). One project = one folder, so there's no "which copy am I editing?" mix-up.

- Checked first: it was empty, and git doesn't track empty folders, so the Desktop repo wasn't affected.
- Used `rmdir`, which **only** deletes empty folders. That makes it safe by design.

---

## ✅ M0 complete

You now have: a Python project, a GitHub repo, checks running on every change, a protected `main`, a briefing note for Claude, and logs of why each piece exists.
**The workflow from here, for every change:** branch → commits → PR → green ✅ → you squash-merge.

---

# M1: Foundations (issue #3)

## M1 Step 1: GitHub issue (2026-11-01)

> **In plain words:** we made a to-do ticket on GitHub (issue **#3**) listing the 6 pieces of M1. Each PR says "Part of #3", and the last one says "Closes #3", which ticks it off automatically.

- Created with `gh issue create` from the terminal.
- **Why #3, not #1?** GitHub numbers issues and PRs **together**, and PRs #1 and #2 came first.
- **Why issues?** One place that says what the work is and why. Progress is visible on GitHub.

## M1 Step 2: Decision records (ADRs) + plan mode (2026-11-01)

> **In plain words:** we wrote 3 short notes saying *"we decided X, because Y"*. We did it with **plan mode**: Claude could only read and plan, you approved the plan, and only then did it write the files.

**What:** `docs/decisions/`
| File | Decision |
|---|---|
| `0001-hsk3-standard.md` | Use HSK 3.0 (2021), bands 1–3 |
| `0002-script-vs-agent.md` | Script if code can check it, agent if it needs judgment (a script checks the agent) |
| `0003-block-contract.md` | Every block = `SPEC.md` + code + tests |
| `README.md` | What an ADR is, plus a template |

**Why:** code shows *what*, ADRs show *why*. They stop people (and Claude) from "fixing" deliberate choices. `CLAUDE.md` now tells Claude to read the relevant ADR first.

**Plan mode (Shift+Tab):**
- Claude **can't change files** in plan mode. It only reads and writes a plan.
- You approve (or change) the plan, and *then* work starts.
- *Why:* you catch a wrong direction before any time is wasted, like agreeing a brief before work begins.

## M1 Step 3: Data shapes (2026-11-01)

> **In plain words:** we made the "forms" every part of the app fills in. A **Card** is one flashcard, a **Mode** says which bits of the card to show, a **Question** is one quiz turn, and a **BlockSpec** is a block's ID card. Python now checks these automatically: a card with no answer, or a mode asking for a missing sentence, fails straight away with a clear message.

**What:**
| Shape | Where | Example |
|---|---|---|
| `Card` | `src/quizkit/models.py` | `id="hsk1-ai", fields={"hanzi": "爱", "pinyin": "ài"}, answers=["to love", "love"], level=1` |
| `Mode` + `build_question()` | `src/quizkit/modes.py` | `char` mode → shows `{"hanzi": "爱"}` |
| `Question` | `src/quizkit/models.py` | shown = 爱, accepted = "to love", "love" |
| `BlockSpec` | `src/quizkit/blocks/base.py` | `name="fetcher", kind="script"` |
| `HSK_MODES` | `src/hsk_trainer/modes.py` | your 4 modes as config |

**Key design choice:** `quizkit` doesn't know about Chinese. A Card has flexible named `fields`, and the HSK side picks the names (`hanzi`, `pinyin`, …). A capitals quiz could use `{"country": "France"}` with the same code.

**Also:** the project now has **two packages**, `quizkit` (generic) and `hsk_trainer` (Mandarin). The run command is now **`uv run hsk`**. Added the **pydantic** library (it does the checking).

**How (test-first):** wrote 16 tests describing the behaviour → ran them ❌ (shapes didn't exist) → wrote the shapes → ran them ✅. Also checked that no Mandarin words appear in `quizkit`.
**Why test-first:** the tests are a precise "brief" for the code, and they keep guarding it forever after.

## M1 Step 4: Settings + hooks (2026-11-01)

> **In plain words:** Claude is now **safer** and **less naggy** in this project. It no longer asks permission for safe everyday commands (like running tests). It **can't touch `.env`** at all, even through a shell command. And every Python file it edits gets **tidied automatically**.

**What:**
| Thing | Type | Where |
|---|---|---|
| Allowlist: tests, ruff, `uv sync`, git/gh *read-only* commands run without asking | Permission rule | `.claude/settings.json` → `allow` |
| `.env` lock: blocks Read/Edit/Write/Grep/Glob on `.env`, and shell commands mentioning it | **PreToolUse hook** (runs *before* a tool) | `.claude/hooks/block_env.py` |
| Auto-tidy: `ruff format` after every `.py` edit | **PostToolUse hook** (runs *after* a tool) | `.claude/hooks/format_python.py` |

**Permission rule vs hook (again, simply):**
- **Rule** = a fixed list: "allow X, deny Y".
- **Hook** = a **little script that runs automatically** before or after Claude uses a tool. It can *block* (exit code 2) or *do something* (like tidy a file).

**"Still the right thing?" check (new habit):** before building, we re-tested the original plan. The first idea ("block anything mentioning `.env`") would have **stopped Claude writing docs** that mention `.env`. So file tools now check only *which file* is touched. Shell commands still check the full text, since it's safer to over-block there.
`CLAUDE.md` now says every plan starts with this check. You can also always say *"challenge this step"*.

**Live tests:**
1. Claude tried to Read `.env` → stopped by **lock 1** (deny rule)
2. Claude tried `cat .env` in the shell → stopped by **lock 2** (the hook): *"Blocked: .env holds secrets…"*
3. Claude made a deliberately messy edit to `cli.py` → the hook **tidied it straight back** (git saw no change)

**Tests:** 19 hook tests in `tests/test_hooks.py` (35 total). Written first: ❌ → scripts → ✅.

**Why:** fewer pop-ups means faster work, but risky things (commit, push, merge) still ask. Two locks on secrets beat one. Auto-tidy means CI's format check never fails.
**Scope:** project only. You had no global hooks, so the financial work is unaffected. Hooks were picked up straight away, with no restart needed.

## M1 Step 5: The `/new-block` skill (2026-11-01)

> **In plain words:** the app is like a **factory line of workers**, and each worker (a **block**) has one job (download the list, make flashcards, mark answers…). `/new-block` = **"hire a new worker"**. Claude asks 3 questions, a script makes the worker's blank folder (job description + code + test), and Claude helps you fill in the job description.

**What a block is:** a small folder with
- 📄 `SPEC.md`: its **job description** (7 sections: Goal, Kind, Inputs, Outputs, Tools, Failure modes, How to test)
- 🐍 the code
- 🧪 a test

**What we built:**
| Piece | Plain meaning | Where |
|---|---|---|
| The skill | Instructions Claude follows when you type `/new-block` | `.claude/skills/new-block/SKILL.md` |
| The "photocopier" script | Makes the blank files, the same way every time; refuses to overwrite; has `--dry-run` | `src/quizkit/scaffold.py` |
| The SPEC checker | Lists any missing sections of a job description | `missing_spec_sections()` in `src/quizkit/blocks/base.py` |

**"Still the right thing?" changes:** the original plan had Claude make the files itself. We split it up instead: making files is **mechanical → a script** (identical every time, tested), and deciding the job is **thinking → Claude, with you**. That's ADR 0002 applied to our own tools. The script lives in `quizkit`, so future quiz projects get it too.

**Tests:** 13 new (48 total), written first ❌ → ✅. Also generated a real demo block, checked that it passed lint and its own test, then removed it.
**Strictness:** the skill is 🔵 guidance (Claude follows it); the script is the reliable part.

## M1 Step 6: Helper subagents (2026-11-01)

> **In plain words:** we made 2 **specialist helpers** that Claude sends off with fresh eyes. The 🧪 **test-writer** writes tests from a block's job description, and the 🔍 **block-reviewer** checks the block and says ✅ ready or ⚠️ fix first. They now run automatically as part of `/new-block`, and their verdict goes into every block PR.

**What:**
| Helper | Job | Can it change files? | Where |
|---|---|---|---|
| 🧪 test-writer | Tests from the SPEC (like an exam written from the syllabus) | Yes, told only in `tests/` 🔵 | `.claude/agents/test-writer.md` |
| 🔍 block-reviewer | ✅ / ⚠️ checklist against the SPEC + ADRs | **No**, its tools are read-only 🔴 | `.claude/agents/block-reviewer.md` |

**When they run (triggers):** `/new-block` steps 6 (test-writer) and 8 (reviewer); the CLAUDE.md rule "no block PR without a ✅ review"; and a PR template checkbox with the verdict pasted in.
*Lesson:* I first built the helpers **without** wiring in when they run. You caught it. From now on, every tool gets planned together with its triggers.

**Live demo:** a pretend block ("how common is a Chinese word") with **2 planted mistakes**: marked as an AI agent when it's a plain lookup, and an empty word not handled.
1. test-writer → wrote 4 tests; 1 failed (the empty word), and it flagged the wrong kind
2. reviewer → **⚠️ fix first**, naming both mistakes with file:line
3. fixed both → all 6 tests pass → re-review → **✅ ready**
4. demo deleted (never committed)

**"Still the right thing?" change:** `data-auditor` (checks AI sentences) moved to **M4**, because there are no sentences until then.
**Watch out:** new subagents only load at session start (`/exit` → `claude --continue`).

---

## ✅ M1 complete
You now have: decision records, data shapes, hooks and permissions, the `/new-block` skill, and 2 helper subagents, all wired together.

---

# M2: Data in (issue #10)

## M2 Step 1: GitHub issue (2026-11-02)
> **In plain words:** to-do ticket **#10** lists the 6 pieces of M2.

## M2 Step 2: Choose the word list → ADR 0004 (2026-11-02)

> **In plain words:** we picked **where the words come from**. Research found a **newer, smaller official word list** (the 2026 revised syllabus), and you chose it. It's free to use (MIT licence) and **locked to one exact version**.

**What we checked:**
| Check | Result |
|---|---|
| Which HSK? | The source has both the 2021 lists and the **2026 revised** lists |
| Allowed to use it? | ✅ MIT licence, so we can re-publish it in a public repo if we keep the notice |
| Complete? | **294 / 491 / 978** words (bands 1 / 2 / 3, cumulative) vs the official **300 / 500 / 1,000**: within 2% |
| Has pinyin + English? | ✅ |
| Locked version? | ✅ commit `7ac65bf…` |

**Why the 2026 list:** it's what the exam tests from 2026. It's smaller (978 words to band 3), so it's quicker to master.
**Honest caveat:** a community contributor typed up the 2026 lists. They match the official totals, but single words could be off. We'll fix any we find.

**Updated:** ADR 0001's counts are now marked as replaced by ADR 0004. README, CLAUDE.md and PLAN now say ~1,000 words.

**Claude features used:**
- **Plan mode as safe research mode:** looked up the source on GitHub (`gh api`) and counted the words, without changing anything
- **Web search** to cross-check the official counts
- **A question with options** for a decision only you could make (which syllabus)

**Lesson for next time:** research the data *before* building. The original plan had the wrong word counts, and checking first saved building a fetcher for the wrong list.

## M2 Step 3: Stronger starter test for new blocks (2026-11-02)

> **In plain words:** every new block's starter test now also checks that the code's **inputs and outputs** match the job description. If someone changes one but not the other, the test fails.

- **Where the idea came from:** the block-reviewer's optional suggestion in the M1 demo (its second review).
- **What changed:** a new helper `spec_section()` (reads one section of a SPEC.md), plus a third starter test, `test_inputs_and_outputs_match_spec`.
- **Proof:** made a real demo block → 3 tests passed. Then changed its inputs without updating the SPEC → the test **failed** with a clear message. Demo deleted afterwards.
- **Caught along the way:** the first version of the template produced lines that were too long for `ruff format`. Testing the *generated* files, not just the script, caught it.
- **No plan mode:** a small, clear fix with no design choices.

## M2 Step 4: The `fetcher` block (2026-11-02)

> **In plain words:** our first real worker. It **downloads the 3 HSK word-list files + the licence** from the pinned version, and **checks each one's size and fingerprint**. Wrong file → it stops and saves nothing. It's also built from a **generic download helper** that any future quiz can reuse.

**What we built:**
| Piece | Plain meaning | Where |
|---|---|---|
| 📥 `fetcher` block | Knows the HSK "shopping list": which files, which version, expected sizes + fingerprints | `src/hsk_trainer/blocks/fetcher/` |
| 🔧 `download_verified()` | Generic: download any file + check it, never leaving a half-file | `src/quizkit/download.py` |
| 📦 The data | 4 files, 914 KB | `data/raw/hsk3_2026/` |

**The full routine, for the first time for real:**
1. `/new-block fetcher` → 3 questions (you chose: script, Chinese-only, **but keep the download part generic**)
2. Job description filled in with you, section by section
3. 🧪 test-writer → 22 tests (18 failing, as expected) + 4 gaps in the job description, which we settled
4. Built the code → all green → **real download** worked; the 2nd run downloaded nothing
5. 🔍 reviewer, **3 rounds**:
   - Round 1 ⚠️: 3 promises had no real test (one safety feature's code never actually ran in tests)
   - Round 2 ⚠️: a disk error didn't name the file
   - Round 3 ✅ ready (+ 2 optional fixes, also done)

**Lessons:**
- **The reviewer earned its keep:** all 3 rounds found real gaps that the passing tests didn't show.
- **Prove a test is real:** we broke the clean-up code on purpose, and the new test caught it.
- **Line endings can break fingerprints:** `.gitattributes` now stores `data/raw/` byte-for-byte.
- Also fixed: the scaffold wrote Windows line endings, and a `sed` command mangled a line (fixed with the editor tool).

## M2 Step 5: The `normalizer` block (2026-11-02)

> **In plain words:** the second worker. It turns the 3 raw word lists into **one tidy file of quiz cards**, `data/processed/cards.jsonl`: one card per word, **978 cards** (band 1: 294, band 2: 197, band 3: 487). Every later step reads only this file.

**What a card looks like** (爱): `id` "爱", `level` 1, `fields` hanzi / pinyin / pos / readings, `answers` = every meaning split at `;` ("to love", "to be fond of", …).

**Decisions we made:**
- **Words with several readings** (197 of them, e.g. 吧 bā / ba / biā): keep them all for now. The source doesn't say which reading HSK means. A `readings` count marks these words in case we add listening practice later (noted under "Future (not v1)" in PLAN.md).
- **HSK exam check:** the quiz trains reading recognition. Listening, writing and grammar are out of scope for v1.
- **Shared helper:** "write to a temp file, then swap it in" moved from the downloader to `quizkit/files.py`, so both blocks use one copy.

**The routine:**
1. `/new-block normalizer` → script, `hsk_trainer`; SPEC written with you, section by section
2. 🧪 test-writer → 21 tests (all failing, as expected) + **7 SPEC gaps**. The big one: may `pos` be empty? Checking the real data showed **11 words have no part of speech**, so the real run would have crashed.
3. Built the code → all green → real run: 978 cards, byte-identical on a second run
4. 🔍 reviewer, **3 rounds, a fresh one each time**:
   - Round 1 ✅ (+3 suggestions, done): disk errors, test gaps, wrong data types slipping through
   - Round 2 ⚠️: a missing or `null` `pos` was quietly accepted, against the SPEC
   - Round 3 ✅ ready

**Lessons:**
- **Look at the real data before writing the SPEC.** My notes had the wrong key names, and the multi-reading problem only showed up by looking.
- **A subagent flags questions, you check them against reality.**
- **Fresh eyes each round** found a gap the first reviewer missed.

## M2 Step 6: The word-count test (2026-11-02), M2 done

> **In plain words:** an automatic test on the **real** `cards.jsonl`. It checks the exact word counts and that the file is up to date, so CI shouts if the data ever changes by accident.

- **Checks:** exact counts per band (294 / 197 / 487, which is 294 / 491 / 978 cumulative), each band within 5% of the official 300 / 500 / 1,000, every word unique, and re-running the normalizer gives exactly the committed file.
- **Proof it's real:** deleting one card → 3 tests failed; a wrong expected number → 1 test failed. Both restored.
- **Not a block,** so no `/new-block`, test-writer or reviewer: just a test file and a PR.
- **M2 is done.** Its lessons are in PLAYBOOK.md under "🎓 Lessons by milestone".

## M3 Step 1: Start of M3, the check and the housekeeping (2026-11-02)

> **In plain words:** before building the quiz, we checked the old plan against what we know now, made two decisions, opened issue #16, and saved the build map in the repo so it can't get lost.

**"Still the right thing?" Yes, with 4 changes:**
- `build_question()` already exists (M1), so the `deck_builder` only has to *pick* cards.
- The answers are raw dictionary text (`"(coll.) father"`, `"to love"`), so the grader must **clean** them first. That's the hardest part, so it comes first.
- Words with several readings show them all in `char_pinyin` (吧 = `bā / ba / biā`). We left it that way on purpose.
- Scores aren't saved until M5. Fine for a first version.

**Your decisions:**
- `--band 2` = only the 197 new band-2 words. "Bands 1+2 together" is noted in PLAN.md for later.
- The marker forgives small typos (`lvoe`) but not wrong words.

**Housekeeping:**
- `docs/build-map/index.html` = the source of the "HSK Trainer Build Map" page. It has a new **"How it grew"** timeline (one line per step).
- CLAUDE.md now says: after each step, update the build map too. This is guidance (🔵): Claude follows it, nothing enforces it.

**The 3 new parts, as a factory line:** `deck_builder` = the dealer (picks the cards), `grader` = the marker (right or wrong?), `engine` = the game host (asks, waits, keeps score). The CLI is the front door.

## M3 Step 1b: The build map shows every kind of part, plus snapshots (2026-11-02)

> **In plain words:** you asked to see *what kinds of things* we've built, where they live, and when each check kicks in. You also wanted to look back at the map as it was after each step.

- **New section 1, "What we've built, by kind":** the **workshop** (Claude Code setup: CLAUDE.md, settings.json, hooks, skill, subagents), the **checks** (tests, ruff, CI, protected main), and the **product** (generic `quizkit` and Mandarin `hsk_trainer`). It also has a small "subagent vs agent" comparison.
- **New section 3, "The journey of one change":** 11 boxes in order, from plan to merge, each naming the tool that does the job. **Code review is shown as a dashed gap**: it was in the plan but never set up.
- **Snapshots:** `docs/build-map/snapshots/` keeps a frozen copy after each step (`m2-done`, `m3-step1`, `m3-step1b`), linked from "How it grew". The map moved to `docs/build-map/index.html`.
- **Subagent vs agent:** a subagent is a helper *inside Claude Code* while we build (test-writer, block-reviewer). An agent is *part of the app*: Python that calls the Claude API by itself. The first one is `sentence_writer` in M4.
- **Later the same day, flow diagrams:** a new section 2 with three views. **A** = how one step gets built, in lanes (you, Claude, helpers, your computer, GitHub), with the red "fail → go back" loops. **B** = what the app does with the words (built now vs planned). **C** = one Claude action up close: hook → permission rules → tool → format hook. Before publishing, I checked them with a headless-browser screenshot. That caught overlapping labels and odd number symbols, which I fixed.
- **Watch-out:** the `.env` hook blocked two shell commands just because their text mentioned `.env`. That's the hook doing its job. The fix: write the text with the Write/Edit tools, or put the script in a file and run that.

## M3 Step 1c: Code review, two layers (2026-11-02)

> **In plain words:** a second pair of eyes on every change. Claude reads the change like a careful teacher and hunts for bugs nobody wrote a test for. It was in the plan since M1 but never wired in (a tool without a trigger), so you spotted a real gap.

| | `/code-review` | Claude GitHub app |
|---|---|---|
| Like | A friend proofreading before you hand in | The teacher who reads every essay handed in |
| Where / when | Here, before the PR | On GitHub, every PR + every push |
| Trigger | CLAUDE.md rule + PR checkbox (🔵) | Runs by itself (🟠) |

**What happened:**
1. You ran `/install-github-app`: it installed the Claude app, saved a **subscription token** as a GitHub secret (`CLAUDE_CODE_OAUTH_TOKEN`), and opened PR #18 with 2 workflow files. You merged it. CI was green. The `claude-review` check was green too, **but it had skipped**: the log says the workflow file must already be on `main` before it runs. Green is not the same as reviewed.
2. I read the 2 files: `claude-code-review.yml` runs a code-review **plugin** (`code-review@claude-code-plugins`) on GitHub and comments on the PR's lines. It's a cousin of the local `/code-review` skill, not the identical thing. `claude.yml` answers `@claude`. (I first told you it could only read and comment. The local review showed that's wrong: it uses the Claude app's own permissions, which may include pushing a branch. Protected `main` still stops it reaching `main`.)
3. Wired in the triggers: CLAUDE.md rule, PR-template checkbox, playbook section 13, strictness table rows.
4. Build map: code review is now solid in all three places (section 1, View A, the journey).

**Good to know:**
- **Review is advice, not a gate.** It can't block a merge. CI + protected `main` are the gates.
- ⚠️ **The token expires after 1 year:** renew before 2027-10-15 (noted in PLAN.md).
- **First live test of `/code-review` (local), before the PR:** 10 findings. The real ones: 2 wrong claims in my docs ("read and comment only", "the same skill"), a vague renewal date, a stale COURSE_MAP row. All fixed. Ideas for the workflow files (stop duplicate runs, check that the review can fetch the PR) go in a **separate PR**, because changing a workflow makes its own review skip.
- **Not fixed, with reason:** outsiders can't spend the token with `@claude`, because the action checks that the commenter has write access to the repo. Fork PRs get no review (GitHub hides secrets from forks); fine for a solo repo.
- `/code-review` is **built into** Claude Code, so there was nothing to install, only a trigger to add.
- **First real GitHub review run (PR #19):** it really ran this time (no skip), but Claude finished in **3 seconds, 2 turns, 0 comments**, and its output is hidden in the log. A real review of this diff would take minutes. So it's **installed but not proven**. Next (Step 1d): a test PR with a **planted bug** to see if it catches it, then fix the workflow file in its own PR.

## M3 Step 1d: Proving the GitHub reviewer works (2026-11-02)

> **In plain words:** we planted 2 bugs in a throwaway PR (#20) to see if the GitHub reviewer catches them. Same trick as testing the subagents in M1.

- **The planted code:** `percent_correct(correct, total)` with 2 bugs: it multiplied by **10 instead of 100**, and it **crashes when total is 0**. The title and description gave no hint.
- **Result:** the review ran for 19 seconds, 5 turns, and left **1 comment** on the exact line: "multiplies by 10, not 100 … `percent_correct(8, 10)` returns 8.0 instead of 80.0", with a one-click fix. ✅
- **Missed:** the divide-by-zero. ❌
- **What it means:**
  - The reviewer **works on code**. On docs-only PR #19 it probably found nothing worth saying (3 seconds, no comments). That's likely, not certain, because its output is hidden.
  - **A reviewer catches some bugs, not all.** Tests are what make a rule certain. That's why the test-writer stays in the routine.
  - The workflow file stays as installed for now. The "don't run duplicate reviews" idea can wait until double runs actually cost us something.
- **Cleanup:** PR #20 was closed with a note, not merged, and its branch deleted.

## M3 Step 2: Marking answers: the grader + the HSK cleaner (2026-11-02)

> **In plain words:** the quiz needs a "teacher" that marks your answer right or wrong. We built it in two parts: a **generic teacher** (the `grader`) and an **HSK answer key tidier** (the `cedict_cleaner`).

1. **Scanned first.** Before building, a throwaway script looked at all 4,110 dictionary answers. Most clutter ("(coll.)", "sb/sth", "surname Bai", "abbr. for …") belongs to *this dictionary* (CC-CEDICT), not to quizzes in general. Only 2 cards (些, 辆) had no typeable answer at all.
2. **So we split the job.** The **grader** (in `quizkit`, reusable for any quiz) handles what every quiz needs: case, spaces, punctuation, a leading "to/a/an/the", and small typos (0 for 1–3 letters, 1 for 4–7, 2 for 8+; a swap like "loev" counts as 1, using the `rapidfuzz` library). A quiz hands it a **cleaner** for its own clutter. The **cedict_cleaner** (in `hsk_trainer`) is that cleaner for our dictionary: 8 rules.
3. **Same loop for each:** `/new-block` → SPEC section by section with you → **test-writer** (50 + 58 tests) → build → **block-reviewer** → fix → re-review.

**Good to know:**
- **The test-writer's guesses showed where the SPEC was vague** (e.g. "is the space counted in the length?"). We fixed the SPEC, not just the code.
- **The real-data test found a bug the toy tests couldn't.** 给 means just "to". The grader stripped a leading "to", leaving nothing, so nobody could ever answer it. Fix: ignore "to" only when more words follow. Lesson: test on the real data, not just examples.
- **The reviewer caught the SPEC contradicting itself** after that fix (an old line still said "typing *to* is always wrong").
- **Synonyms** ("papa" for 爸爸) aren't accepted unless the dictionary lists them. That needs judgment, so it's an agent's job.
- **Your call: rules are a stopgap.** You'd rather have judgment than rule sets. Plan: in **M4**, an offline **answer agent** writes each card's answer list with synonyms (a script checks it, you spot-check, it gets committed), replacing the cleaner. You also want **sentence translation** one day, which needs a judgment agent for grading. Both are in PLAN.md.
- **Known weak spots (left for the agent):** 得 picks up junk from a colon list ("degree"); 吧 accepts "smack!".
- **`/code-review` before the PR: 10 findings, 5 fixed.** I checked each against the real data first. Fixed: 下午 = "p.m." couldn't be answered with "pm" (dots in abbreviations now removed); "email" vs "e-mail" said "check spelling" (an exact match now ignores spaces, 62 hyphenated meanings); a note before "surname" slipped past rule 1; other apostrophe characters; rare Chinese characters. Skipped, with reasons: comma synonyms (3 real cases, the answer agent replaces it), typing "classifier for vehicles" in full (nobody does), "hour" accepted for "four" (the agreed 1-typo trade-off; the play-test will tell), "sb/sth" (0 cases), speed (978 cards is tiny). Lesson: **check a finding against the real data before fixing it**, which sorts real bugs from theoretical ones.

## M3 Step 3: The deck builder, built next to the engine with a worktree (2026-11-02)

> **In plain words:** the `deck_builder` is the quiz's "dealer": it picks which cards you get. We built it while a **second Claude session** built the engine at the same time, each in its own folder.

1. **"Still the right thing?"** It's small today (filter, pick, make questions), but it's its own block because in M5 "what's next?" gets smart (your idea: wrong words come back more, recent ones wait). Then only this block changes. `levels` is a list, so "bands 1+2 together" costs nothing later.
2. **Your idea logged:** future ideas now have their own list, `docs/FUTURE.md` (smart deck, mistake log, answer agent, sentence translation, bands together, listening). CLAUDE.md says to add new ideas there.
3. **The worktree:** `git worktree add -b m3-engine ../mandarin-hsk-trainer-engine main` made a second folder on its own branch. You opened a second terminal and started `claude` there with a starter prompt. Rule: only this session edits the shared docs.
4. **Same block loop:** `/new-block` → SPEC (all 7 sections at once, since we'd agreed the design) → **test-writer** (27 tests, toy capitals + a real-data check: band 2 asked for 500 → all 197) → built first try → **block-reviewer** ❌ then ✅.

**Good to know:**
- **The reviewer caught drift:** I added a SPEC line ("levels 1 and 99: use what's there") *after* the test-writer was done, so no test covered it. Lesson: a SPEC change after the tests means a new test.
- **Printing is the CLI's job**, not a generic block's: asking for more cards than exist just gives a shorter list, and the CLI will say "only 197 band-2 words".
- **`/code-review`: 7 findings, all handled.** Fixed: a duplicated card could come up twice (now unique by id, first copy wins, tested); a card the mode doesn't fit only crashed *if drawn*, so sometimes yes, sometimes no (now every card at the chosen levels is checked first); `n=2.0` or `True` slipped through (now a `TypeError`); two tests each loaded the real cards their own way (now one shared `real_cards` helper in `tests/conftest.py`); a test hard-coded 197 (the count is pinned once, in `test_word_counts.py`); dead code. The 7th (docs not done yet) was just timing. Lesson: **"works most of the time" bugs hide behind randomness**; check everything up front so failures are repeatable.

## M3 Step 4: The engine, built by a second Claude session in parallel (2026-11-02)

> **In plain words:** the `engine` is the **quizmaster**: it shows each question, takes your answer, asks the grader, and keeps score. A second Claude session built it in its own folder (a git worktree) while this session built the deck builder.

1. **Two layers**, so the same quizmaster works in a terminal now and on a web page later (M6):
   - `QuizSession` = the brain (which question, mark it, keep score). No keyboard or screen code.
   - `run_quiz(questions, ask, tell, cleaner, settings)` = the voice: a short loop that gets each answer from `ask` and shows feedback with `tell`. The CLI will pass real typing and printing; tests pass fake answers. `ask` returning nothing (`None`) means "quit".
   - Results are frozen records: `Attempt` (one answer) and `QuizResult` (correct / answered / total / finished).
2. **Same loop:** `/new-block` → SPEC with you → **test-writer** (28 tests, 35 after fixes) → build → **block-reviewer** ✅ (3 minor fixes) → **`/code-review`** (7 findings, 3 fixed: bad cards are found before question 1, not mid-quiz; the questions are copied so nothing outside can change them; settings made once) → reviewer ✅ again → PR #24 → CI green, GitHub review "No issues found".
3. **Worktree, end to end:** the engine branch started before Step 3 merged, so before its PR it ran `git merge origin/main` (no conflicts, because it only added new files). After the merge I removed the extra folder: `git worktree remove ../mandarin-hsk-trainer-engine`.

**Good to know:**
- **The secrets-file hook fired in both sessions:** the engine session's `gh pr create` and my own log entry were blocked because their text mentioned the secrets file. Same fix both times: write the text with the Write/Edit tools (and `--body-file` for PRs). The safety net works in every session, because it's in git.
- **Parallel work paid off:** two blocks reviewed and merged in about the time of one. The cost: an extra terminal to manage, a starter prompt, and one "update from main" step.
- **Carry to Step 5 (CLI):** Ctrl-C or end-of-input must become a quit, or the score so far is lost.

## M3 Step 5: The CLI, the first playable quiz (2026-11-02)

> **In plain words:** you can now study: `uv run hsk quiz --band 1 --mode char --n 10` shows 10 band-1 words, you type the English, it marks each one and gives a score.

1. **"Still the right thing?"** Yes, with three changes: only `char` and `char_pinyin` can run (the sentence modes need M4 sentences, so the CLI refuses them politely); Chinese output on Windows needed care; and the two Step 4 carry-overs went in here (Ctrl-C keeps the score, short decks say so).
2. **Typer** (`uv add typer`): it gives `--help` for free and a test helper, `CliRunner`, that types fake answers into the program.
3. **Not a block.** The CLI does no reusable job; it's the dashboard that wires the blocks to your keyboard. So no SPEC / test-writer / block-reviewer, but it has its own tests (`tests/test_cli.py`, 31) and `/code-review` still ran.
4. **New generic helper:** `quizkit.files.load_cards(path)` reads a `cards.jsonl`. The shared test setup now uses it, and the Step 6 capitals quiz will too.

**Good to know:**
- **Tests caught three real bugs before review:** wrong answers showed "havent" (the grader's matching form, not for people); piping the output crashed on 爱 (Windows' old code page, fixed by forcing UTF-8, checked by running it with and without the fix); and the cards file was only found from the project folder.
- **`/code-review` ran in the background** and found 8 things. Fixed 6: the typo message still showed "havent"; on Windows a Ctrl-C can arrive *just after* typing and lose the score (now the whole loop catches it, so the CLI drives `QuizSession` itself instead of `run_quiz`); a broken cards file printed a traceback; the "run the normalizer" hint was wrong from other folders; a slow test search; near-duplicate answers shown. Skipped 2, with reasons in the PR (installed-package paths; the test helper copying the deck logic on purpose).
- **Each fix was proved:** running the new tests against the old CLI made 5 of them fail.
- **CI caught what my machine couldn't:** the `--help` test passed here but failed on GitHub, because there `rich` colours the help text and the colour codes split up `--band`. Reproduced locally with `GITHUB_ACTIONS=true uv run pytest`, then the test strips colour codes. The GitHub review ran (about 1 minute) and said "No issues found".

## M3 Step 6: Play-test + reuse check, M3 done (2026-11-02)

> **In plain words:** you played the quiz (it works, but marking answers needs judgment, not rules), and a tiny "capitals of the world" quiz proved the reusable parts really are reusable. M3 is finished.

1. **Play-test.** Both modes work (`--mode char` and `--mode char_pinyin`). Your verdict: the rule-based answer cleaner isn't enough; it needs judgment. That's the M4 **answer agent**, already planned. Tip: note answers that get marked wrongly, as they'll be its test set (now in `docs/FUTURE.md`). One surprise: `! uv run hsk quiz` ends at once, because the `!` shortcut has no keyboard attached, so the quiz sees "end of input" and quits (as designed). Play in a normal terminal.
2. **Reuse check:** `examples/capitals_quiz.py` (France → Paris) uses only `quizkit`: its own cards, its own mode, no cleaner. Run it with `uv run python examples/capitals_quiz.py`. It needed **zero changes** to `quizkit`.
3. **Guards, so it stays true:** `tests/test_reuse.py` (4 tests). One scans every `quizkit` file and fails if any imports `hsk_trainer`. Another plays the capitals quiz in a fresh Python where `hsk_trainer` is **blocked**, so a hidden dependency would crash it. Proved by planting `from hsk_trainer.modes import HSK_MODES` in the engine: both tests went red. Then it was removed.
4. **M3 lessons** written in `docs/PLAYBOOK.md`.

5. **Engine fix (your call: fix now, not in M6).** The reuse check showed the shared quiz loop (`run_quiz`) could lose the score on a late Ctrl-C, so every quiz would copy the CLI's workaround. Full block routine: SPEC updated → **test-writer** (4 new tests, 2 old ones updated; they failed before the fix) → the fix (a `try/except` around the loop) → **block-reviewer**. The HSK CLI now uses `run_quiz` again.

**Good to know:**
- **A second rough edge stays logged** in `docs/FUTURE.md`: the grader only gives the matching form ("havent"), so every front end must rebuild the readable answers. Natural to fix in M6, when the web page needs the same thing.
- **`/code-review` on this step: 9 findings.** Fixed 7: the capitals quiz now prints safely through Windows pipes, shows the right spelling after a typo, and says "Stopped after N of M"; the reuse test no longer depends on the example's prompt wording or quiz length; a second scan catches *hidden* imports (`importlib.import_module("hsk_trainer")`), proved with a planted one (the `/new-block` tool may name the package as text: allowed, with its reason); plus the engine fix above. One was out of date (said the docs were missing; they were written while it ran).
- **A second `/code-review` after the engine change: 7 findings, 4 fixed.** The CLI's "bad cards file" message could have swallowed an unrelated error mid-quiz (now the data check runs before the quiz, on its own); Ctrl-C is now handled only by the engine (the CLI and the example handle just end-of-input themselves); a safety guard on the example's UTF-8 switch; the reuse test can't hang. Kept on purpose: the engine treating Ctrl-C as a quit (a quiz always has a person at the keyboard, and `finished=False` shows it stopped early). Skipped: two tiny timing windows with nothing to lose.
- **The test-writer spotted a test-suite trap:** if a test lets a real Ctrl-C escape, pytest thinks *you* pressed Ctrl-C and silently stops the whole run. Its helper turns that into a normal test failure.

## M4 Step 1: A stronger "Still the right thing?" check (2026-11-02)

> **In plain words:** before each piece of work we ask "is the original plan still right, given what we know now?". That used to be a line in CLAUDE.md, easy to skip. Now an issue and a PR can't go through without an answer.

1. **"Still the right thing?" for M4 (issue #28).** Yes, with one change of order: the **answer agent** comes before `sentence_writer`. The play-test showed grading is the weak spot, and it's a smaller first agent to learn on. The `data-auditor` subagent moved here from M1.
2. **Issue form** (`.github/ISSUE_TEMPLATE/step.yml`): "New issue" on GitHub now shows a form with a required "Still the right thing?" box. Blank issues are off (`config.yml`).
3. **PR template:** a new "Still the right thing?" section.
4. **CI check** (`.github/scripts/check_pr_body.py`): reads the PR description and fails if that section is missing or empty (the template's hint comment doesn't count). It's a step in the existing `check` job, which protected `main` already requires, so no settings change. CI now also re-runs when a PR description is **edited**, so fixing it turns CI green. 22 tests in `tests/test_pr_body.py`.

**Good to know:**
- **The form only works on the website.** `gh issue create` (what Claude uses) skips forms, so Claude must write the section itself. The PR check catches everyone, whatever tool they use.
- **The check proves an answer was written, not that it's a good one.** The thinking is still ours; the gate just makes sure the question is asked every time.
- **Safe with untrusted text:** the PR description is passed to the script as an environment variable, never pasted into the workflow, so a crafted description can't run code.
- **`/code-review` found 10 things; 7 fixed.** Any heading (not just `## `) ends the section; heading variants like `### Still the right thing? (yes)` count; `## ` lines inside code blocks are ignored; an unclosed `<!--` hint doesn't count as an answer (GitHub hides it too); a second, filled-in copy of the section counts; a newer CI run cancels an older one on the same PR; CLAUDE.md notes that `gh pr create --body` skips the template. Kept as known limits: a PR could edit the checker script itself (so read any diff to it), a title-only edit re-runs all tests, and bot PRs (e.g. `@claude`) need the section added by hand.

## M4 Step 2: ADR 0005, how grading gets judgment (2026-11-02)

> **In plain words:** we decided how the quiz will know "dad" is right for 爸爸. Claude writes a list of good answers once, ahead of time; and when your answer isn't on the list, the quiz asks Claude to judge it and remembers the verdict.

1. **"Still the right thing?" changed the plan.** The plan was an answer list only. You pointed out that the later *sentence translation* idea can't work with a fixed list. True: sentence *hint* modes still ask for the word's meaning (a list works), but translating a sentence has endless right answers. So the **judge**, planned for M5, moves into M4.
2. **Two layers** (ADR 0005): the list answers most cases instantly and offline; the judge handles the rest, and later, sentence translation.
3. **Under your subscription, no API key:** both call Claude through `claude -p` (Claude Code run from a script). Tested first: a call takes ~8 s and reports its tokens (the dollar figure it prints is the list-price equivalent, not a charge).

**Good to know:**
- The judge needs internet when it's asked. Without it the answer just stays wrong with "couldn't check"; the quiz never breaks.
- Code can't check that a verdict is *right*, only that its shape is. So verdicts are shown on screen and saved for review.
- This **refines ADR 0002** (agents = "Claude API + tools") rather than editing it: accepted ADRs aren't edited; the new one says what it changes.

## M4 Step 3: answer_writer, the first agent (2026-11-02)

> **In plain words:** Claude wrote the English answers a learner might type for all 978 words (爸爸 → father, dad, papa, daddy, pa), once, and they're saved in `data/generated/answers.jsonl`. It's a static file: no Claude is needed while you study.

1. **"Still the right thing?"** Yes, as in ADR 0005.
2. **`/new-block answer_writer`** (an agent, in `hsk_trainer`), SPEC written section by section with you.
3. **Shared helper `quizkit.claude.ask_claude`:** runs `claude -p` with **no tools** (Claude can only answer, never touch files), from an empty temporary folder (so it doesn't read the project), and returns the text and token counts. Tested with a fake, so tests never call Claude. The judge reuses it.
4. **test-writer** wrote 46 tests from the SPEC (and found 9 gaps in it, all settled); then the code; **block-reviewer** round 1 ⚠️ (7 small fixes, e.g. a broken `answers.jsonl` line now stops with a clear message), round 2 ✅ (plus 4 small extras).
5. **Trial: 20 band-1 words in 8 seconds.** Your verdict: a bit generous ("rude" for 不客气) is fine.
6. **Full run:** 25 calls, ~148k tokens (list-price equivalent ~$0.80, covered by the subscription). The **checker caught 9**: "from小" (Chinese mixed in), "bathroom" twice, 11+ answers for 好 / 等 / 过 / 行, and "p.m." / "mr." / "e.g.". Two changes after that: full stops are now allowed (the grader ignores punctuation anyway), and repeats in a reply are removed rather than failing the card. Re-runs only asked for the failed words.
7. **Spot-check:** 20 random words from all bands, approved.

**Good to know:**
- **Run it:** `uv run python -m hsk_trainer.blocks.answer_writer --limit 20 --dry-run` (shows what it would send). Without `--dry-run`, it only asks for words not already in the file, so re-running is cheap.
- **The quiz doesn't use the file yet.** That's Step 4, together with the judge.
- A test checks the committed file covers all 978 cards, so a half-finished file can't be merged.
- **`/code-review` found 10 things; all 10 fixed.** The big one: Claude often wrote both "love" and "to love", which the grader treats as one answer, so repeats are now spotted the way the grader compares answers; 110 words were tidied **without calling Claude**. Also: saved lines are re-checked on every run (a bad hand edit, a line listed twice, or an older `PROMPT_VERSION` means that word is asked again, so bumping the prompt version really redoes the answers); a removed card's line is deleted from the file; one card missing `answers` fails alone; `claude` exiting with an error code is always an error; the summary still prints when Claude stops the run; two small tidy-ups. Then a **3rd block-reviewer round** (the code had changed since its ✅): ✅ again, plus 3 small fixes (a line saved 3+ times, `--dry-run` never touches the file, the "log in" hint kept). 470 tests.

## M4 Step 4a: one answer list (2026-11-03)

> **In plain words:** the quiz now marks your answer against **one** list: the answers Claude wrote (`answers.jsonl`). The old rule-based cleaner is deleted. "dad" for 爸爸 counts; "modem" for 猫 no longer does.

1. **"Still the right thing?" changed the plan.** ADR 0005 said: accept Claude's answers **plus** the old cleaner's, "so nothing is lost". Before building it we measured: the old list added 1,434 answers on 456 words, mostly senses a learner isn't taught (猫 "modem", 二 "stupid", 块 "soap"). You asked for one simple, traceable list → **ADR 0006** (PR #34). ADR 0005 is marked "partly superseded"; accepted ADRs aren't rewritten.
2. **Find every trace first.** A search for every mention of the old design, sorted into delete / change / keep as history (ADRs, this log and snapshots stay as they were).
3. **The code (PR #35):** the quiz reads answers through `answer_writer.load_answers()`, which checks the file with the writer's own checker; `cedict_cleaner` (63 tests) and the grader's and engine's `cleaner` slot are deleted; a **guard test** (`tests/test_retired.py`) fails if the old names or the slot come back.
4. **The safety fix the review found:** the quiz now needs a line for every word, but the answer writer could shrink the file (after a prompt-version change, a `--limit` run kept only the words it redid). Now an old line stays until a new one replaces it. A bad line only blocks its own band.
5. **Reviews:** test-writer → build → block-reviewer for grader ✅, engine ✅, answer_writer ✅ (3 rounds). `/code-review` twice on the whole branch: 18 findings, 13 fixed, the rest explained in the PR. The GitHub review: "No issues found."

**Good to know:**
- **Block reviews vs whole-change review.** Each block-reviewer looked at one block and said ✅. Only `/code-review`, looking at the whole change, saw the risk *between* blocks (the CLI needs a full file that the writer could shrink). Both layers matter.
- **Kept simple on purpose:** the dictionary text in `cards.jsonl` is still called `answers`; renaming it to `meanings` is in `docs/FUTURE.md`.
- **See CI here:** `! gh pr checks 35` (add `--watch` to wait for it).
- 447 tests (was 470: the cleaner's 63 went with it).
