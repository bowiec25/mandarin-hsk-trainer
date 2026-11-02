# Future extensions

Ideas for after v1 (or later milestones), so they don't get lost. Each line says **what**, **why**, and **what already makes it easier**. When one gets planned into a milestone, move it to `docs/PLAN.md` and mark it here.

| Idea | Why | Already makes it easier | Where it would go |
|---|---|---|---|
| **Smart "what's next" deck** (added 2026-11-02) | Study what you need: words you often get **wrong** come back more, words seen **recently** wait, words you know well fade out | `deck_builder` is its own block (M3 Step 3), so only it changes; M5's `progress_store` logs every attempt (right/wrong, when) | M5: `progress_store` + Leitner boxes, then a smarter `deck_builder` |
| **Mistake log / stats** (added 2026-11-02) | See your weak words, your accuracy per band, and your progress over time | Same attempt log as above | M5: `hsk stats` |
| **Answer agent** (added 2026-11-02) | Clean answer lists *with synonyms* ("papa" for 爸爸), replacing the hand-written cleaner rules | The grader takes any `cleaner`; the rule cleaner is a stopgap | **Planned: M4** (needs an ADR) |
| **Sentence translation** (added 2026-11-02) | Translate whole sentences, not just words | M4 writes the sentences; M5 adds the agent grading fallback | Needs a **judgment agent** for grading, with cached verdicts so the quiz stays offline-first |
| **Several bands together** (added 2026-11-02) | e.g. a bands 1+2 review quiz | `deck_builder` takes a *list* of levels, so the CLI only needs a new option | CLI option after M3 |
| **Stricter SPEC-name check** (added 2026-11-02, from the engine session) | The contract test checks that each `BLOCK_SPEC` input/output name appears *somewhere* in the SPEC, so a short name like `n` passes too easily | `quizkit.blocks.base.spec_section` already isolates each section | Match backticked names (`` `n` ``) in the scaffold's contract test, then re-run it for every block |
| **Fully frozen results** (added 2026-11-02, from the engine session) | `Grade.expected` and `Question.accepted_answers` are lists, so code could still edit them inside a "frozen" model (the engine is already safe: it deep-copies its questions and `QuizResult.attempts` is a tuple; this is about the grader and the models) | The models are pydantic and already `frozen=True` | Switch those lists to tuples (like `GradeSettings.ignore_leading`); update tests |
| **Listening practice** | Hear words and sentences read aloud (text-to-speech) | Stable card ids (audio files named after them), modes as config (a new `listen` mode), the `readings` field flags multi-reading words | A new mode + an audio block |
