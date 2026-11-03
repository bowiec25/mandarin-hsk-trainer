# Block: `engine`

> **In plain words:** Run a quiz: show each question, mark the typed answer with the grader, and keep score.

## Goal
Run a quiz: show each question, mark the typed answer with the grader, and keep score.

It is the **quizmaster**. It takes a list of `Question`s (from `deck_builder`, or anywhere else), and for each one it shows the question, takes the answer, asks the `grader` if it's right, and records the result. At the end it gives a score plus a record of every answer.

It comes in two layers, so the same quizmaster works in a terminal now and on a web page later (M6):
- **`QuizSession`** (the brain): which question you're on, mark an answer, keep score. No keyboard or screen code.
- **`run_quiz`** (the voice): a short loop that gets each answer from an `ask` function and shows feedback through a `tell` function. The CLI passes real typing and printing; tests pass fake answers.

**Not in scope (yet):** picking or shuffling questions (`deck_builder`), saving progress between quizzes (M5 `progress_store`), retrying wrong answers (M5 spaced repetition).

## Kind
**script.** Code can check the output: given these questions and these typed answers, the score and the record must be exactly what we expect. Marking is the `grader`'s job (also a script), so no language judgment is needed here. It runs on every quiz turn, so it must be free and instant (ADR 0002).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `questions` | `list[Question]` | The quiz, in order (e.g. from `deck_builder`) |
| `settings` | `GradeSettings \| None` | Passed straight to the grader. `None` (default) = the grader's default `GradeSettings()` |
| `ask` *(run_quiz only)* | `Callable[[Question], str \| None]` | Shows one question and returns what was typed. Returns **`None` to quit** |
| `tell` *(run_quiz only)* | `Callable[[Attempt], None]` | Shows feedback after each answer |
| `judge` | `Judge \| None` | Optional (M4 Step 4b, ADR 0007): asked only when the grader says wrong and the answer isn't blank. Any `(Question, str) -> Verdict`, e.g. `quizkit.blocks.judge.ClaudeJudge`. `None` (default) = grader only |

**How it's called** (all importable from `quizkit.blocks.engine`):
```python
# the brain, step by step (web page later)
session = QuizSession(questions, settings=None, judge=None)
session.current         # the Question being asked now (None when finished)
session.answer("love")  # marks it, moves to the next question, returns the Attempt
session.done            # True when every question has been answered
session.result()        # the QuizResult so far

# the voice: the whole loop in one call (CLI)
run_quiz(questions, ask, tell, settings=None, judge=None) -> QuizResult
```

These choices keep screen code out of the engine:
- **`ask` returns `None` to quit.** The front end decides which key means quit; the engine just stops.
- **Ctrl-C (`KeyboardInterrupt`) anywhere in the loop is also a quit** (added M3 Step 6, after the reuse check). On Windows, Ctrl-C can arrive just *after* `input()` returns, while grading or inside `tell`, so catching it only in `ask` isn't enough. `run_quiz` catches it around the whole loop, so every quiz built on it keeps the score without copying a workaround.
- **`tell` gets the whole `Attempt`**, not a ready-made sentence. The CLI writes the words ("✓ Correct!" / "✗ The answer was: love"), so a web page can show it its own way.

## Outputs
Everything is returned in memory as pydantic models (frozen). Nothing is saved to a file; saving is M5's `progress_store`.

**`Attempt`**: one answered question
| Field | Type | Plain meaning |
|---|---|---|
| `question` | `Question` | What was asked |
| `typed` | `str` | Exactly what the learner typed (not cleaned) |
| `grade` | `Grade` | The grader's verdict (correct, matched, typo, expected) |
| `verdict` | `Verdict \| None` | The judge's verdict (correct, reason, source); `None` if the judge wasn't asked |
| `correct` | `bool` (computed) | Right by the grader, **or** the judge said yes |

**`QuizResult`**: the whole quiz
| Field | Type | Plain meaning |
|---|---|---|
| `attempts` | `tuple[Attempt, ...]` | Every answer, in the order asked (a tuple, so answers can't be added or removed afterwards) |
| `total` | `int` | How many questions the quiz had (at least 1, and never fewer than `answered`) |
| `correct` | `int` (computed) | How many attempts are `correct`. A typo-forgiven or judge-accepted answer **counts as right** |
| `answered` | `int` (computed) | `len(attempts)`, less than `total` if the learner quit early |
| `finished` | `bool` (computed) | `answered == total` |

Example: quit after 3 of 10 with 2 right → `correct=2, answered=3, total=10, finished=False`. The CLI can then show "2 / 3 (quit early, 7 not asked)".

## Tools
- **`quizkit.blocks.grader.grade`**: does all the marking. The engine never compares answers itself.
- **`quizkit.models.Question`**: the input shape.
- **pydantic**: `Attempt`, `QuizResult`.
- No files, no network, no agent. It doesn't import `deck_builder` or anything from `hsk_trainer`.

## Failure modes
| Situation | What it does |
|---|---|
| `questions` is empty | **Raises `ValueError`** when the session is created, so `run_quiz([])` raises before calling `ask` (a quiz with nothing in it is a bug upstream, so it must be loud) |
| `ask` returns `None` (quit) | Stops at once and returns the result so far (`finished=False`). Quitting before question 1 (the first `ask` returns `None`) gives 0 answered, no crash |
| Blank answer `""` | **Not** a quit: the grader marks it wrong and it counts as answered |
| `session.answer()` called after the last question | **Raises `RuntimeError`** (a bug in whatever is calling the engine) |
| `KeyboardInterrupt` (Ctrl-C) raised anywhere in `run_quiz`'s loop: in `ask`, while grading, or in `tell` | **A quit:** `run_quiz` stops and returns the result so far (`finished=False`). An answer already marked counts (even if `tell` was interrupted while showing it); an answer interrupted while being marked doesn't. `ask`/`tell` are not called again |
| `KeyboardInterrupt` while the session is being **created** (before the loop, e.g. during the up-front check) | Passed through: the quiz hasn't started, so there is no score to keep |
| The grader raises mid-quiz (anything but Ctrl-C) | Passed through, not swallowed (a bug must be loud), and `run_quiz` returns nothing |
| `ask` or `tell` raises anything else (e.g. `ValueError`) | Passed through, not swallowed (a bug must be loud), and `run_quiz` returns nothing |
| `QuizSession` (the brain) and Ctrl-C | Not its job: the brain has no loop, so whoever drives it step by step handles Ctrl-C |
| A card nobody can answer | Found **when the session is created**, before question 1 (each question is graded once with a blank answer), so the grader's error is raised before `ask` is called and no answers are lost mid-quiz. A data bug must be loud, as in the grader's SPEC |
| The same question appears twice | Asked twice, both recorded (removing repeats is `deck_builder`'s job) |
| A `QuizResult` built by hand with `total` < 1 or more attempts than `total` | pydantic **rejects** it (`ValidationError`), so a result is trustworthy outside `QuizSession` too (e.g. M5's progress store) |
| The caller changes its `questions` list, or a question's answers, after starting | No effect: the session keeps its own deep copy |

## How to test
Automatic tests in `tests/blocks/test_engine.py`. They use toy English questions only (e.g. capitals), to prove the engine is generic, and **fake typed answers**: `ask` comes from a list (`iter(["Paris", "rome", None])`) and `tell` just collects what it's given. No real keyboard.
- **Full quiz:** 3 questions, 2 right → `correct=2, answered=3, total=3, finished=True`; attempts in order, `typed` kept exactly as typed
- **Typo counts as right:** `"Pariss"` for "Paris" → correct, `grade.typo=True`
- **Quit:** `None` after 1 answer → `answered=1, finished=False`, and `ask` isn't called again; `None` straight away → 0 answered
- **Blank answer** is wrong, not a quit
- **`tell`** is called once per answer, with that answer's `Attempt`, and not after a quit
- **Settings are passed through** (`allow_typos=False` makes `"Pariss"` wrong)
- **Step by step:** `current` moves forward, `done` flips, `answer()` after the end → `RuntimeError`, `result()` partway works
- **Ctrl-C is a quit, anywhere in the loop:** `KeyboardInterrupt` from `ask` after 1 answer → `answered=1`; before question 1 → `answered=0`; from `tell` on answer 2 → that answer still counts (`answered=2`), `ask` not called again; while answer 2 is being marked → it doesn't count (`answered=1`); the result is returned, nothing raised. But Ctrl-C while the session is being **created** → passed through, `ask` never called
- **Errors:** empty list → `ValueError`; any other error from `ask`, `tell` or the grader is passed through
- **Own copy:** changing the list, or a question's answers, after starting has no effect
- **Bad card found early:** an unanswerable question 2 raises before `ask` is ever called
- **Result can't change:** `attempts` can't be appended to; a hand-built `QuizResult` with bad numbers is rejected
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

Manual check: none here. The real feel is checked in the M3 Step 6 play-test, through the CLI.
