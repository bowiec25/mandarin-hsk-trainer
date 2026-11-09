# 0013: Progress saved per word and skill; Leitner boxes decide which words come next

- **Status:** Accepted (2026-11-10; the user: "I like this Leitner box system")
- **In plain words:** Every answer you give is saved on your computer. Each word has a **box** (1–5) for each of two skills: recognising the word, and understanding it in a sentence. Right moves it up a box, wrong sends it back to box 1, and higher boxes wait longer before the word comes back. A new quiz deals the words that are **due** first, then new words. `hsk stats` shows how you're doing.

## Context
- The plan's M5: `progress_store`, Leitner spaced repetition, `hsk stats`. FUTURE.md adds: "words you often get wrong come back more, words seen recently wait", and a mistake log.
- The user's choice (2026-11-09): **track by word + skill**. Two skills: `recognise` (char, char_pinyin, char_sentence, full) and `sentence` (translate, translate_pinyin). Knowing 爱 by its characters shouldn't push it out of translation practice.
- What the blocks already give (checked first, the playbook lesson from ADR 0012):
  - the engine's `Attempt` has the question (card, mode), what was typed, the grade (incl. typo) and the judge's verdict with its `source` (`claude`, `cache`, `self`, `not_checked`);
  - `QuizResult.skipped` (words with no sentence: never asked);
  - `deck_builder` only filters and shuffles, so it needs a new input to prefer due words;
  - `run_quiz` calls `tell` once per marked answer, right after marking.
- `data/progress.db` is already gitignored (personal, not shared).

## Decision
1. **A generic `progress_store` block (quizkit, script):** SQLite at `data/progress.db`. It knows nothing about Chinese.
   - `attempts`: one row per answer: when (UTC), card, skill, mode, typed, right or wrong, and **who decided** (`grader`, `typo`, `claude`, `cache`, `self`, `not_checked`).
   - `boxes`: one row per (card, skill): box, when it's next due, last seen, right and wrong counts.
   - Each answer is saved in one transaction, as soon as it's marked (the CLI's `tell`), so a crash or Ctrl-C loses at most the answer being shown.
2. **The skill is config:** `Mode.skill: str` (default `"default"`). HSK sets `recognise` on the 4 word modes and `sentence` on the 2 translate modes. There's no `if mode == ...` in the code.
3. **Leitner boxes (5 boxes):**
   - Right → up one box (max 5); wrong → box 1.
   - Wait before due: box 1 = now, box 2 = 1 day, box 3 = 3 days, box 4 = 7 days, box 5 = 21 days.
   - A word never seen has no box ("new").
   - A **"couldn't check"** answer (the judge failed, or you didn't mark it) is saved, and counts as wrong in that quiz's score. It **doesn't move the box**: we don't know.
   - A typo-forgiven, judge-accepted or self-marked "yes" counts as right.
   - The rule lives in one pure function (`next_box(box, correct) -> (box, wait)`), so it's easy to test and change.
4. **Which words next:** `deck_builder` gets an optional schedule, each card's due time for this quiz's skill. It deals, in order:
   1. due words, most overdue first;
   2. new words, shuffled;
   3. if `n` isn't filled yet, words not due yet, soonest first.

   No schedule = today's shuffle. `--seed` still makes it repeatable.
5. **CLI:**
   - Saving is on by default; `--no-save` practises without saving or reading progress.
   - The quiz end line adds "3 words moved up, 1 back to box 1".
   - `hsk stats [--band N]`: per band and skill, how many words are new / in each box / due now; accuracy over the last 7 days; your 10 most-missed words.
6. **Not in this milestone:** missed *sentences* coming back sooner (FUTURE.md; ADR 0011's bank pick), and a web view (M6).

## PR plan (small PRs)
1. This ADR.
2. `progress_store` block (`/new-block`, test-writer → build → block-reviewer).
3. Leitner `next_box` + `deck_builder` schedule input (block change: test-writer → build → block-reviewer).
4. CLI wiring (`Mode.skill`, saving in `tell`, `--no-save`, the end line) + `hsk stats`.
5. Docs + M5 lessons + build map; data-auditor at the milestone end.

## Why / alternatives considered
- **Track by word only:** simpler, but a word you recognise would leave translation practice too early (the user chose word + skill).
- **Track by every mode:** char and char_pinyin are almost the same skill, so words would come back twice as often as needed.
- **SM-2 / Anki-style ease factors:** finer, but harder to explain and to test. Leitner is 5 boxes and one table; we can swap the rule later (it's one function).
- **A JSON file instead of SQLite:** fine for 1,000 words, but SQLite gives safe writes (one transaction per answer), easy queries for stats, and it's in Python's standard library.
- **Save at the end of the quiz:** loses everything on a crash; saving each answer costs about a millisecond.
- **Recording inside the engine:** the engine stays free of files (it's reused by the capitals quiz and M6); the front end saves what it's told.

## Consequences
- ✅ Quizzes adapt to you: missed words come back, known words fade out, and each skill is tracked on its own.
- ✅ A full history (who decided each answer) for stats now and smarter choices later (e.g. folding judge verdicts into the answer list, FUTURE.md).
- ⚠️ A new file holds your progress. It's local and gitignored, so it's not backed up: deleting it starts over.
- ⚠️ Box waits are a guess (1/3/7/21 days). Adjust them after real use; they live in one place.
