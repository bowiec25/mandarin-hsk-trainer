# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project
A vocab trainer for **HSK 3.0, bands 1–3** (2026 revised syllabus, 978 words; ADR 0004), built as reusable "blocks". The full plan and current progress are in `docs/PLAN.md` (read the "Where we are" checklist first). `docs/SETUP_LOG.md` records the reason behind each setup step.
Ideas for later live in `docs/FUTURE.md`: when the user mentions a future idea, add it there.
Big decisions live in `docs/decisions/` (ADRs). Read the relevant ADR before changing that area. A new big decision gets a new ADR; don't edit an accepted one.

## Commands
- `uv sync`: install the project and dev tools from `uv.lock`
- `uv run hsk`: run the CLI (real commands arrive in M3)
- `uv run ruff check` / `uv run ruff format`: lint / format (CI runs `ruff format --check`)
- `uv run pytest`: all tests. A single test: `uv run pytest tests/test_smoke.py::test_packages_import`
- `uv add <pkg>` / `uv add --dev <pkg>`: add a dependency. Never use `pip install`.

Before saying work is done, run `ruff check`, `ruff format --check` and `pytest`. CI (`.github/workflows/ci.yml`) runs the same checks with `uv sync --locked`.

## Architecture (target, from docs/PLAN.md)
- `src/quizkit/`: **generic**, reusable for any quiz (block contract, Card/Question models, modes, engine, grader, progress). No Mandarin-specific code here.
- `src/hsk_trainer/`: **Mandarin-specific** (HSK source, pinyin, sentence-agent prompt, CLI).
- Every block is a folder containing `SPEC.md` (Goal, Kind, Inputs, Outputs, Tools, Failure modes, How to test), the code, and tests. Inputs and outputs are pydantic models.
- Question modes are **config**, not branching code: `char`, `char_pinyin`, `char_sentence`, `full`.
- Data: `data/raw/` → `data/processed/cards.jsonl` → `data/generated/sentences.jsonl` (all committed). `data/progress.db` is gitignored.

## Script vs agent rule
If code can check that the output is correct, write a **script**. If the task needs language judgment, use an **agent**, and a script must validate its output.
Agents run offline as batch jobs that write to `data/generated/` for review. They call deterministic script functions as tools, take `--limit N` / `--dry-run`, and log model, prompt version and token cost. The quiz must not need the API at runtime, except two optional uses that always have a fallback and an off switch: the judge (ADR 0007, `--no-judge`) and live sentences (ADR 0011, `--no-live`; every live sentence is checked by the same scripts before it is shown).

## Workflow
- The user is learning. Work in small steps: explain What / Why / Claude feature / Checkpoint, then stop for a go-ahead.
- Every plan starts with a **"Still the right thing?"** check: re-test the original plan against what we know now, and say what changed. It is also a required section in every issue (`.github/ISSUE_TEMPLATE/step.yml`) and PR; CI fails a PR whose section is empty (`.github/scripts/check_pr_body.py`). `gh issue create` skips the form and `gh pr create --body` skips the template, so write the section yourself. Known limit: a PR could weaken the checker script itself, so read any diff to it.
- After each step, tick `docs/PLAN.md`, add a plain-English entry to `docs/SETUP_LOG.md`, update `docs/COURSE_MAP.md` (course topic coverage), and update the build map: edit `docs/build-map/index.html` (tiles, diagrams, gates, tests table, plus one line in "How it grew"), save a frozen copy as `docs/build-map/snapshots/<step>.html` linked from that line (in the copy, strip `snapshots/` from the timeline links, since the copy already lives there), and republish the folder to the "HSK Trainer Build Map" artifact (slug `b2990603-08ad-441e-86c9-93eef6ba9d50`). When a step adds a reusable safety net, check, permission, hook, skill or subagent, also add it to `docs/PLAYBOOK.md` (the user's checklist for future projects). At the **end of each milestone**, fill in its entry under "🎓 Lessons by milestone" in the playbook: what was built, plus 3–7 "think about next time" points.
- Never commit to `main` directly once it's protected (M0 Step 6). Use issue → branch → small commits → PR → green CI → merge. The user approves merges.
- Secrets live in `.env` (gitignored; Claude is denied reading it). Document new keys in `.env.example`.
- New blocks: always use `/new-block` (it runs `uv run python -m quizkit.scaffold`). Never hand-create block folders.
- Every new or changed block: **test-writer** subagent (tests from the SPEC) → build until green → **block-reviewer** subagent → fix until ✅ ready → PR with its verdict pasted in. Don't open a block PR without a ✅ review.
- Code review, two layers (M3 Step 1c): **before opening any PR**, run `/code-review` on the branch, fix real findings (or say why not), and put a one-line result in the PR. On GitHub, `.github/workflows/claude-code-review.yml` then reviews every PR automatically and comments on the lines; read those comments before the user merges. `@claude` in a PR or issue asks the GitHub app (it works with the app's own permissions, so it may push a branch; protected `main` still stops it reaching `main`). The GitHub review only runs once its workflow file on the branch matches `main`, so a PR that changes the workflow gets a green but skipped review. Green is not the same as reviewed: check the run log. Review is advice, not a gate: CI and protected `main` are the gates.
- Hooks (`.claude/hooks/`, tested in `tests/test_hooks.py`): `block_env.py` blocks any tool or shell command touching `.env`, and `format_python.py` runs `ruff format` after every `.py` edit. If a shell command mentioning `.env` is blocked, that's intended: write docs with the Edit/Write tools instead.
