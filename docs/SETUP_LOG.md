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
