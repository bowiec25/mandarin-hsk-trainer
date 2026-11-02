## What
<!-- One or two sentences: what does this PR change? -->

## Why
<!-- Link the issue (e.g. "Closes #3") and say why this change is needed. -->

## Still the right thing?
<!-- Required (CI fails if empty). What changed from the plan, and why? Or "Nothing changed, because ...". -->

## How tested
<!-- Commands run, what you checked by hand. -->

## Checklist
- [ ] `uv run ruff check` and `uv run ruff format --check` pass
- [ ] `uv run pytest` passes
- [ ] New/changed blocks have an up-to-date `SPEC.md`
- [ ] New/changed blocks: tests from the **test-writer** subagent, and the **block-reviewer** subagent says ✅ ready (paste its verdict below)
- [ ] `/code-review` run on the branch before this PR (result below), and the automatic Claude review comments on this PR read before merging
- [ ] No secrets (`.env`, API keys) in the diff
- [ ] `docs/PLAN.md` checklist updated if a step/milestone finished
