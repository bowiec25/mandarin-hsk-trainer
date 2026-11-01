---
name: new-block
description: Create a new block (one part of the app with one job) in this project. It makes the blank folder, SPEC.md and contract test with the scaffold script, then fills in the SPEC with the user. Use when the user types /new-block or asks to add or create a new block, part or component (e.g. fetcher, normalizer, grader).
argument-hint: "[block_name] [--dry-run]"
---

# /new-block: hire a new worker for the app

**In plain words:** a *block* is one worker with one job (e.g. download the word list). This skill sets up a new worker's folder the same way every time: a job description (`SPEC.md`), the code file and a test. Then it helps the user write the job description.

Follow these steps **in order**. Keep the wording simple. The user is learning, so stop after each question.

## 1. Get the basics
From the arguments (`$ARGUMENTS`) or by asking:
- **Name:** `snake_case`, e.g. `fetcher`, `sentence_writer`
- **Goal:** one plain sentence: what is its one job?

If the arguments include `--dry-run`, remember it: nothing is written in step 4.

## 2. Script or agent? (ADR 0002, `docs/decisions/0002-script-vs-agent.md`)
Ask: **"Can code check that its output is right?"**
- Yes → `script`
- No, it needs language judgment → `agent` (remind them: a script must then validate its output, and it needs `--limit` / `--dry-run`)
Give your recommendation and a one-line reason, and let the user decide.

## 3. Which package? (ADR 0003, `docs/decisions/0003-block-contract.md`)
Ask: **"Would a quiz about something else (e.g. capitals) need this too?"**
- Yes → `quizkit` (generic: no Chinese words allowed inside)
- No, it's Mandarin-specific → `hsk_trainer`

## 4. Make the files (the script does this, not you)
First a dry run, and show the user the list:
```
uv run python -m quizkit.scaffold <name> --kind <kind> --package <package> --goal "<goal>" --dry-run
```
- If the user asked for `--dry-run`, **stop here**: say nothing was created, and summarise what would happen.
- Otherwise, after the user OKs it, run the same command **without** `--dry-run`.
- Don't create or edit these files by hand. The script makes them identical every time.
- If the script says the block already exists, stop and tell the user. Never delete or overwrite it.

## 5. Fill in SPEC.md together
Open `src/<package>/blocks/<name>/SPEC.md`. Go through the sections **one at a time** (Goal, Kind, Inputs, Outputs, Tools, Failure modes, How to test):
- Suggest a short draft for the section, then ask the user to OK or change it
- Replace the `<!-- TODO -->` comment with the agreed text
- Keep each section short and plain
Then copy the inputs and outputs into `BLOCK_SPEC` in the block's `__init__.py`.

## 6. Check and wrap up
- Run `uv run pytest tests/blocks/test_<name>.py` (the contract test must pass)
- Tell the user, in plain words, what was created and what's next (build `run()`, test-first)
- Remind them of the routine: this belongs on a **branch** → PR → CI ✅ → squash-merge. If they're on `main`, offer to create a branch first.
