# Course Map: this project vs *Claude Code in Action*

Where each course topic shows up in this project. ✅ = done for real here · 🔜 = planned (milestone).
Topic names follow the course's main themes. Rename rows to match your lesson titles if they differ.

| Course topic | Status | Where we used it | What you actually did / saw |
|---|---|---|---|
| **Running commands / the terminal** | ✅ | M0 Steps 1–2 | `!` prefix for interactive commands (`! gh auth login`); Claude runs non-interactive ones itself after a permission prompt |
| **Status line & subagents (first look)** | ✅ | M0 Step 6b | `/statusline` → a `statusline-setup` **subagent** configured a project-only status line showing the branch |
| **Context & `CLAUDE.md`** | ✅ | M0 Step 4d | Ran `/init`, trimmed the result to ~35 lines of rules + commands; opened it with `/memory` |
| **Memory hierarchy** | ✅ | M0 Step 4d | Project `CLAUDE.md` (shared) vs `CLAUDE.local.md` (personal, gitignored) vs `~/.claude/CLAUDE.md` (all projects) vs auto-memory |
| **Permissions & settings** | ✅ | M0 Step 4a, M1 Step 4 | `.claude/settings.json` with `deny: Read(./.env)`; committed so it's shared; `settings.local.json` for personal overrides; M1: **allowlist** of safe read/test commands (commit/push/merge still ask) |
| **Verification loops** (letting Claude check its own work) | ✅ | M0 Step 4b, M1 Step 3 | ruff + pytest added; Claude runs them after changes; CI repeats them on GitHub; M1 Step 3: **tests first**, ran them ❌, wrote the code, ran them ✅ |
| **Git workflow with Claude** | ✅ | M0 Steps 4e–6 | First commit with Conventional Commit message + `Co-Authored-By: Claude`; branch protection on `main`; first branch + PR (#1) |
| **GitHub integration** | ✅ / 🔜 | M0 Step 5 ✅, Step 6, later | `gh repo create --push`; token scopes (`workflow`); `gh run watch` + `gh run view --log-failed` to debug CI; branch protection next; later `/install-github-app` for `@claude` in PRs |
| **Plan mode** | ✅ | M1 Step 2 | Pressed Shift+Tab → Claude could only read and plan → you approved the plan → then it wrote the ADRs |
| **Custom commands & skills** | ✅ | M1 Step 5 | Built `/new-block` (`.claude/skills/new-block/SKILL.md`): the skill does the thinking (questions, SPEC drafting), and a tested **script** (`quizkit.scaffold`) makes the files. Tried it with `--dry-run` |
| **Subagents** | 🔜 | M1 | `block-reviewer`, `test-writer`, `data-auditor` in `.claude/agents/` |
| **Hooks** | ✅ | M1 Step 4 | **PreToolUse** `block_env.py` (live test: `cat .env` → blocked); **PostToolUse** `format_python.py` (live test: messy edit → tidied automatically). Scripts are plain Python with their own tests |
| **Code review** | 🔜 | M1 onwards | `/code-review` on every PR before merge |
| **Session management** | 🔜 | when relevant | `/clear`, `/compact`, `--continue` / `--resume`, one session per task |
| **Parallel work (worktrees)** | 🔜 | M3 | Two Claude sessions on two features via git worktrees |
| **MCP servers** | 🔜 | optional | Not needed yet. Candidate later: a GitHub or browser MCP for testing the M6 web UI |
| **Claude API / Agent SDK** | 🔜 | M4–M5 | `sentence_writer` agent with tool use; optional grading fallback |
