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
