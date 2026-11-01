# 0003: The block contract

- **Status:** Accepted (2026-11-01)
- **In plain words:** the app is built from small parts called **blocks**. Every block looks the same: a `SPEC.md` that says what it does, the code, and tests. That makes blocks easy to understand, check and reuse.

## Context
We want reusable pieces: a future "Spanish verbs" or "finance terms" quiz should reuse most of this project. Pieces are only reusable if each one clearly says what goes in, what comes out, and how to test it. We also want Claude (the `/new-block` skill and the `block-reviewer` subagent) to build and check blocks the same way every time.

## Decision
**Every block is a folder containing:**
1. `SPEC.md` with these sections: **Goal**, **Kind** (script / agent), **Inputs**, **Outputs**, **Tools**, **Failure modes**, **How to test**
2. The code
3. Tests

**Rules:**
- Inputs and outputs are **typed pydantic models** (e.g. `Card`, `Question`), not loose dicts.
- **Generic** blocks go in `src/quizkit/` (models, modes, engine, grader, progress). They must contain no Mandarin-specific code.
- **Mandarin-specific** blocks go in `src/hsk_trainer/` (fetcher, normalizer, sentence writer/validator, CLI).
- Question modes are **config** (`MODES = {"char": ["hanzi"], …}`), not `if` branches.

## Why / alternatives considered
- **Free-form modules:** quicker at first, but every part ends up different, so it's harder to review and reuse.
- **One big package:** simpler, but the generic parts get tangled up with Mandarin details and can't be reused.

## Consequences
- ✅ A new quiz only needs a new fetcher + normalizer. The rest is reused from `quizkit`.
- ✅ `/new-block` (M1) can create the folder from a template, and `block-reviewer` can check a block against its SPEC.
- ✅ The SPEC doubles as documentation and as the source for tests.
- ⚠️ A bit more ceremony for tiny blocks: the SPEC is still required, but it can be short.
- 🔍 Reuse is tested at the end of M3 by building a toy second deck (e.g. country capitals) using only `quizkit`.
