# 📘 New Project Playbook

**What this is:** every safety net, check and Claude setting we used, explained simply, so you can **copy them into any new project**.
Each item says: **what it is**, **why you want it**, **what to ask Claude for**, and **where it lives** in this repo, so you can copy it.

> **How to use it:** start a new project, open this file, and work down the checklist. Or just tell Claude:
> *"Set up this project using the playbook at github.com/bowiec25/mandarin-hsk-trainer/blob/main/docs/PLAYBOOK.md"*

---

## ✅ Quick checklist

**Once per computer** (already done on this PC)
- [ ] Tools installed: `git`, `gh` (GitHub CLI), `uv` (Python)
- [ ] `gh auth login` (include the `workflow` permission)
- [ ] Git name + **noreply** email set
- [ ] (Optional) `git config --global init.defaultBranch main`

**Every new project**
*(🔴 hard rule · 🟠 automatic · 🔵 guidance · ⚪ habit, explained in "How strict is each thing?" below)*
- [ ] 1. Project + git started on `main`
- [ ] 2. 🔒 Secrets protected (`.gitignore` 🟠, `.env.example` ⚪, push protection 🔴)
- [ ] 3. ✅ Checks installed: lint, format, tests (🔵 locally)
- [ ] 4. 🧑‍⚖️ CI on GitHub runs the checks (🔴 once `main` is protected)
- [ ] 5. 🛡️ `main` protected + squash-merge + auto-delete branches (🔴)
- [ ] 6. 🤖 `CLAUDE.md` briefing note (🔵)
- [ ] 7. 🤖 Claude permissions: allowlist + deny (🔴, Claude only)
- [ ] 8. 🤖 Hooks: secrets lock 🔴 + auto-format 🟠 (Claude only)
- [ ] 9. 📝 Docs: README, decision records, PR template (⚪)
- [ ] 10. 🔁 The working routine: issue → branch → PR → merge (⚪, but 🔴 enforced at merge)
- [ ] 11. 🤖 Skills for repeated jobs, e.g. `/new-block` (🔵, with the mechanical part in a script)

---

## 🚦 How strict is each thing?

Some of these **physically stop** a mistake. Others are just **instructions or habits** that someone has to follow. Know which is which.

| Level | Meaning | Can it be ignored? |
|---|---|---|
| 🔴 **Hard rule** | A machine **blocks** the action | No (only by changing the setting itself) |
| 🟠 **Automatic** | Runs by itself and **fixes** things, but doesn't block | Not usually, but it only covers what it's set up for |
| 🔵 **Guidance** | Instructions Claude **reads and normally follows** | Yes: Claude can miss or misjudge it |
| ⚪ **Habit** | Good practice **people** choose to do | Yes, easily |

### The full list
| Thing | Strictness | Enforced by | When it kicks in | Applies to | ⚠️ Limits |
|---|---|---|---|---|---|
| `main` protection (PR + CI required) | 🔴 | GitHub | Every push or merge to `main` | **Everyone**, incl. you (admins included) | A repo admin can switch it off in Settings |
| Squash-only, auto-delete branches | 🔴 | GitHub | When merging | Everyone | Same as above |
| Push protection (API keys) | 🔴 | GitHub | Every push (public repos) | Everyone | Only spots *known* key formats; you can override online |
| "Block pushes that expose my email" | 🔴 | GitHub | Every push | You | Has to be ticked in GitHub settings |
| `deny` permission (`Read(./.env)`) | 🔴 | Claude Code | Every time Claude uses that tool | **Claude only** | Covers only the listed tool (Read), so it can't stop shell commands. That's why we added the hook |
| Secrets-lock hook | 🔴 | Claude Code (our script) | **Before** every Claude tool use | **Claude only** | Only blocks what the script recognises; project-only |
| Plan mode | 🔴 | Claude Code | While it's switched on | Claude only | Only if **you** turn it on (Shift+Tab) |
| "Ask before acting" (anything not on `allow`) | 🔴* | Claude Code | Every tool use | Claude only | *Depends on the permission mode: some modes ask less. `deny` and hooks still apply in every mode |
| CI checks on GitHub | 🟡 → 🔴 | GitHub | Every push and PR | Everyone | On its own it only *reports* ❌. It **blocks** only because `main` protection requires it |
| `.gitignore` (hides `.env`) | 🟠 | git | When files are added | Everyone | `git add -f` forces a file in anyway |
| Auto-format hook | 🟠 | Claude Code (our script) | **After** Claude edits a `.py` file | **Claude only** | Your *own* edits in VS Code aren't tidied, but CI catches them |
| `allow` list | (loosens) | Claude Code | Every tool use | Claude only | Makes things *less* strict: only list safe read/test commands |
| Skills (`/new-block`) | 🔵 | Claude following SKILL.md | When you type the command (or Claude spots a match) | Claude only | Not enforced, so the file-making is done by a tested script |
| `CLAUDE.md` rules | 🔵 | Claude reading it | Start of every session | Claude only | Not enforced: Claude can forget or misjudge. Make anything important a 🔴 rule or hook |
| Running ruff/pytest locally | 🔵 / ⚪ | Claude (per CLAUDE.md) or you | When someone runs them | Whoever runs them | Nothing forces it locally. CI is the real gate |
| ADRs, PR template | ⚪ | People | When writing PRs / decisions | Everyone | Just a form to fill in |
| "Still the right thing?", small steps | ⚪ | You + Claude | Each plan | Everyone | A habit |

### The big lesson
- **If it really matters, make it 🔴.** E.g. "Don't read `.env`" in CLAUDE.md is only 🔵, but the deny rule plus the hook makes it 🔴.
- **Claude-only vs everyone:** permissions and hooks only control **Claude**. Only **GitHub** settings stop **everyone**, you included.
- **Layers beat one lock:** for secrets we have `.gitignore` 🟠 + deny 🔴 + hook 🔴 + push protection 🔴.

💬 **Ask Claude for a new project:** *"For each safety measure, tell me whether it's a hard rule, automatic, guidance or a habit, and who it applies to."*

---

## 1. Project + git

| What | Why | Ask Claude | Where here |
|---|---|---|---|
| `uv init --package` | Makes a proper Python project (settings file, `src/` folder, Python version pinned) | *"Set up a uv package project"* | `pyproject.toml`, `src/` |
| `git init` on branch `main` | Starts the change history | *"Start git on main"* | `.git/` |
| `.gitattributes` with `* text=auto eol=lf` | Stops Windows vs Linux line-ending warnings | *"Add a .gitattributes for LF endings"* | `.gitattributes` |

⚠️ **Watch out:** `uv init` starts git itself, on `master`. Check with `git branch --show-current`.

---

## 2. 🔒 Secrets

| What | Why | Where here |
|---|---|---|
| `.env` in `.gitignore` | Your API keys never get uploaded | `.gitignore` |
| `.env.example` (key **names**, no values) | Shows what's needed without leaking anything | `.env.example` |
| Commits use your **noreply** email | Keeps your real email off the internet | git config |
| GitHub → Settings → Emails → **"Block command line pushes that expose my email"** | A safety net if you forget | GitHub website |

**Ask Claude:** *"Make sure secrets can't be committed, and add a .env.example"*
**Public repos** also get GitHub **push protection** for free: it blocks pushes that contain API keys.

---

## 3. ✅ Checks (the "validation")

**These are scripts, not AI.** They just pass or fail.

| Check | Like… | Command |
|---|---|---|
| `ruff check` | A spell-checker for code | `uv run ruff check` |
| `ruff format` | Auto-format in Word | `uv run ruff format` |
| `pytest` | A checklist of "does it work?" | `uv run pytest` |

**Why:** Claude can **check its own work** and fix mistakes before you see them (the "verification loop").
**Ask Claude:** *"Add ruff and pytest as dev tools with a smoke test"*. Then later: *"Write the tests first, show me they fail, then write the code."*
**Where here:** `pyproject.toml` (dev deps), `tests/`

---

## 4. 🧑‍⚖️ CI (GitHub runs the checks)

| What | Why | Where here |
|---|---|---|
| A workflow file that runs the checks on every push and PR | Proves the code works on a **clean computer**, not just yours | `.github/workflows/ci.yml` |

**Ask Claude:** *"Add a GitHub Actions CI that runs ruff and pytest with uv"*
⚠️ **Watch out:**
- Your `gh` login needs the **`workflow`** permission to upload CI files (`gh auth refresh -s workflow`)
- Third-party actions: **pin to a commit SHA**, not a tag (a tag can be moved to different code)
- Ask Claude to **look up current versions**, not guess them

**Debug a failure:** `gh run view <id> --log-failed`

---

## 5. 🛡️ Protect `main`

| Setting | Plain meaning |
|---|---|
| Require a PR | Changes go on a side branch first |
| Require CI to pass | Can't merge if ❌ |
| Include admins | The rules apply to you too |
| No force-push / no delete | History can't be wiped |
| **Squash merge only** | One tidy commit per PR |
| **Auto-delete branches** | No leftover branches |

**Ask Claude:** *"Protect main: require a PR and passing CI, include admins, squash-only, auto-delete branches"*
⚠️ **Watch out:** on GitHub's **free plan**, branch protection only works on **public** repos (private needs Pro).
**Test it:** try pushing straight to `main`. It should be **rejected**.

---

## 6. 🤖 `CLAUDE.md`: the briefing note

| What | Why |
|---|---|
| A short file that Claude reads at the start of **every** session | Claude knows your rules and commands without being told again |

**Ask Claude:** run `/init`, then *"trim it to the essentials and add our rules"*
**Keep it short:** every line costs space in every session.

| File | For | Shared? |
|---|---|---|
| `CLAUDE.md` | Everyone on this project | ✅ committed |
| `CLAUDE.local.md` | Just you, this project | ❌ gitignored |
| `~/.claude/CLAUDE.md` | You, **all** projects | n/a |

**Edit it with** `/memory`. **Where here:** `CLAUDE.md`

---

## 7. 🤖 Claude permissions

**Where:** `.claude/settings.json` (shared) or `.claude/settings.local.json` (just you)

| Type | Plain meaning | Example here |
|---|---|---|
| `allow` | "Don't ask me every time" | `uv run pytest`, `git status`, `gh pr view` |
| `deny` | "Never do this" | `Read(./.env)` |
| *(everything else)* | Claude **asks** first | commit, push, merge, delete |

**Rule of thumb:** only `allow` commands that **read or test**. Anything that **changes, uploads or deletes** should still ask.
**Ask Claude:** *"Add an allowlist for safe read and test commands, and deny reading .env"*

---

## 8. 🤖 Hooks: automatic little scripts

**Rule vs hook:** a **rule** is a fixed allow/deny list. A **hook** is a **script that runs automatically** before or after Claude uses a tool. It can **block** something or **do** something.

| Hook | When | Does | Where here |
|---|---|---|---|
| Secrets lock | **Before** any tool (PreToolUse) | Blocks anything touching `.env`, even shell commands | `.claude/hooks/block_env.py` |
| Auto-tidy | **After** an edit (PostToolUse) | Runs `ruff format` on the edited `.py` file | `.claude/hooks/format_python.py` |

**Ask Claude:** *"Copy the block_env and format_python hooks from my mandarin-hsk-trainer repo, with their tests"*
**Check they're on:** `/hooks`
⚠️ **Watch out:**
- **Test hooks** like any code (here: `tests/test_hooks.py`), then **live-test** them (e.g. have Claude try `cat .env`)
- Blocking by "mentions `.env`" is too broad, because it stops Claude writing docs. Check the **file path** for file tools, and only the **command text** for shell commands.
- Hooks live in **project** settings, so other projects aren't affected

---

## 9. 📝 Docs

| File | For | Why |
|---|---|---|
| `README.md` | **Humans** | What it is, how to run it |
| `CLAUDE.md` | **Claude** | Rules and commands |
| `docs/decisions/` (ADRs) | Future you | "We chose X because Y", so it doesn't get undone by accident |
| `.github/pull_request_template.md` | Reviewers | Every PR: What / Why / How tested / Checklist |

---

## 10. 🔁 The routine (every change)

```
issue → plan mode → branch → small commits → PR → CI ✅ → squash-merge
```

| Step | How |
|---|---|
| Issue | *"Create an issue for X"* (`gh issue create`) |
| **Plan mode** | **Shift+Tab**. Claude only reads and plans until you approve |
| Branch | Claude makes it, and the status line shows which one you're on |
| PR | Claude writes it from the template; `Part of #N` / `Closes #N` |
| Merge | `! gh pr merge <n> --squash` (after a look at `gh pr diff <n>`) |

**Habits that pay off:**
- Every plan starts with **"Still the right thing?"**, and you can ask Claude to *"challenge this step"*
- Ask Claude to **verify** things rather than assume (e.g. look up versions, run the checks)
- One small step at a time, then stop and check

---

## 11. 🤖 Skills: your own slash commands

**Plain meaning:** a **skill** = **saved instructions** that become a command. You type `/new-block` and Claude follows the same steps every time, so you don't have to explain them again.
**Strictness:** 🔵 guidance. Claude follows the steps, but nothing *blocks* it from going off-script. So put the important, mechanical part in a **script** (🔴-ish reliable).

| Skill here | What it does | Where |
|---|---|---|
| `/new-block` | "Hire a new worker": asks 3 questions → a **script** makes the blank files → Claude helps fill in the job description (SPEC.md) → tests run | `.claude/skills/new-block/SKILL.md` + `src/quizkit/scaffold.py` |

**When to make a skill:** if you've **explained the same thing to Claude 2–3 times**, turn it into a skill.

**3 ways to make one:**
| Way | When |
|---|---|
| ⭐ *"Turn what we just did into a skill called /X"* | **The best way:** do the task once by hand, then save it |
| *"What skills would help in this project?"* | You're not sure what would help |
| The **`skill-creator`** skill | Bigger skills: it helps write, test and improve them |
| Write `SKILL.md` yourself | It's just a text file with instructions |

**The trick that makes skills reliable: skill + script**
- ✍️ **Claude (the skill)** does the *thinking*: asking questions, drafting text
- 🖨️ **A script** does the *mechanical* part: making files, always identical, with tests
- That's ADR 0002 (script vs agent) applied to your own tools

**What makes a good skill:**
- A clear **description** saying *when* to use it (Claude reads it to decide when to trigger the skill)
- Numbered steps, plus **"stop and ask"** points
- A **dry-run** option, so you can try it safely
- Safety rules written in: "never overwrite", "dry run first"

💬 **Ask Claude:** *"Make a project skill called /<name> that does X. Put the mechanical part in a tested script, and give it a dry-run option."*
📍 **Where skills live:** `.claude/skills/<name>/SKILL.md` = this project only (committed, shared). `~/.claude/skills/` = all your projects.
⚠️ **Watch out:** a skill is only as good as its instructions. Try it once with a dry run before relying on it.

---

## 🧰 Other Claude features we've used

| Feature | Plain meaning | How |
|---|---|---|
| `!` prefix | You run a command, and the output lands in the chat | `! gh auth login` |
| Status line | A bar showing folder + **branch** + model | `/statusline` (project-only: `.claude/settings.local.json`) |
| Subagent | A helper Claude for one narrow job, running in the background | Used for the status line; more in M1 Step 6 |
| Auto-memory | Claude remembers how you like to work, across sessions | Automatic |

*Coming soon here:* **build subagents** (reviewer, test-writer).
