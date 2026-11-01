# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project
A vocab trainer for **HSK 3.0, bands 1–3**, built as reusable "blocks". The full plan and current progress are in `docs/PLAN.md` (read the "Where we are" checklist first). `docs/SETUP_LOG.md` records the reason behind each setup step.
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
Agents run offline as batch jobs that write to `data/generated/` for review. They call deterministic script functions as tools, take `--limit N` / `--dry-run`, and log model, prompt version and token cost. The quiz must not need the API at runtime (except the optional grading fallback).

## Workflow
- The user is learning. Work in small steps: explain What / Why / Claude feature / Checkpoint, then stop for a go-ahead.
- Every plan starts with a **"Still the right thing?"** check: re-test the original plan against what we know now, and say what changed.
- After each step, tick `docs/PLAN.md`, add a plain-English entry to `docs/SETUP_LOG.md`, and update `docs/COURSE_MAP.md` (course topic coverage).
- Never commit to `main` directly once it's protected (M0 Step 6). Use issue → branch → small commits → PR → green CI → merge. The user approves merges.
- Secrets live in `.env` (gitignored; Claude is denied reading it). Document new keys in `.env.example`.
- Hooks (`.claude/hooks/`, tested in `tests/test_hooks.py`): `block_env.py` blocks any tool or shell command touching `.env`, and `format_python.py` runs `ruff format` after every `.py` edit. If a shell command mentioning `.env` is blocked, that's intended: write docs with the Edit/Write tools instead.
