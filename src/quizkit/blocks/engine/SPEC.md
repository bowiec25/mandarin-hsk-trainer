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
**script.** Code can check the output: given these questions and these typed answers, the score and the record must be exactly what we expect. Marking is the `grader`'s job (also a script), so no language judgment is needed here. An optional judge (an agent, ADR 0007) can be plugged in; the engine only calls it, never Claude directly, so the engine itself stays a script. It runs on every quiz turn, so its own work must be free and instant (ADR 0002); a plugged-in judge may add a wait on a wrong answer (the CLI shows "asking the judge…").

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `questions` | `list[Question]` | The quiz, in order (e.g. from `deck_builder`) |
| `settings` | `GradeSettings \| None` | Passed straight to the grader. `None` (default) = the grader's default `GradeSettings()` |
| `ask` *(run_quiz only)* | `Callable[[Question], str \| None]` | Shows one question and returns what was typed. Returns **`None` to quit** |
| `tell` *(run_quiz only)* | `Callable[[Attempt], None]` | Shows feedback after each answer |
| `judge` | `Judge \| None` | Optional (M4 Step 4b, ADR 0007): asked only when the grader says wrong and the answer isn't blank. Any `(Question, str) -> Verdict`, e.g. `quizkit.blocks.judge.ClaudeJudge`. `None` (default) = grader only |
| `prepare` | `Callable[[Question], Question \| None] \| None` | Optional (ADR 0012): **finishes a question just before it is asked**, for questions whose content only exists then (e.g. a sentence written live, whose English is the answer). Called **once per question**, the first time the session needs it: reading `current` or `done`, or calling `answer()` before either (then it is prepared first, before anything is marked). Never when the session is created, and never after an answer is marked, so a `prepare` error can't lose the answer just given. If `prepare` itself raised (or Ctrl-C), the next read tries that question again; if it returned something unusable (see Failure modes), the same `ValueError` is raised again without calling `prepare` again (no repeated side effects). The questions given must still be answerable themselves (the up-front check grades them), e.g. the word's own question in translate mode. Returns the question to ask instead (it must be for the same `card_id`), or **`None` to skip it** (not asked, not scored). `None` (default) = every question is asked as given |

**How it's called** (all importable from `quizkit.blocks.engine`):
```python
# the brain, step by step (web page later)
session = QuizSession(questions, settings=None, judge=None, prepare=None)
session.current         # the Question being asked now, prepared (None when finished)
session.answer("love")  # marks it, moves to the next question, returns the Attempt
session.done            # True when every question has been answered
session.result()        # the QuizResult so far
session.can_own_mark    # True if the last answer is waiting for your own mark
session.own_mark(verdict, card_id=None)  # your own mark on the last answer (ADR 0014)

# the voice: the whole loop in one call (CLI)
run_quiz(questions, ask, tell, settings=None, judge=None, prepare=None) -> QuizResult
```

These choices keep screen code out of the engine:
- **`ask` returns `None` to quit.** The front end decides which key means quit; the engine just stops.
- **Ctrl-C (`KeyboardInterrupt`) anywhere in the loop is also a quit** (added M3 Step 6, after the reuse check). On Windows, Ctrl-C can arrive just *after* `input()` returns, while grading or inside `tell`, so catching it only in `ask` isn't enough. `run_quiz` catches it around the whole loop, so every quiz built on it keeps the score without copying a workaround.
- **`tell` gets the whole `Attempt`**, not a ready-made sentence. The CLI writes the words ("✓ Correct!" / "✗ The answer was: love"), so a web page can show it its own way.
- **Your own mark comes after the answer, not inside it** (ADR 0014). A terminal can ask "Did you get the gist?" inside a judge call, but a web page can't pause in the middle of `answer()`. So `answer()` marks as usual; if nobody could check it, the front end asks you, then calls `own_mark(verdict)` with a `Verdict` whose `source` is `"self"`. It replaces the **last** answer's verdict in the record and returns the updated `Attempt`. It doesn't move the quiz on. A **blank** answer can't take your mark (nothing was typed, and the judge skips blanks too). A `"self"` verdict that came through the judge (the terminal's prompt) already counts as checked. A refused mark changes nothing. Pass `card_id` (the question the mark is for): if the last answer is for another card, it raises `ValueError`, so a late or repeated click on a web page can't mark the wrong answer (it can't tell apart two answers to the same card in a row, but `deck_builder` never deals a card twice). **Save an answer once it's final:** after `own_mark` when the front end asks for your mark, not straight after `answer()`.

## Outputs
Everything is returned in memory as pydantic models (frozen). Nothing is saved to a file; saving is M5's `progress_store`.

**`Attempt`**: one answered question
| Field | Type | Plain meaning |
|---|---|---|
| `question` | `Question` | What was asked |
| `typed` | `str` | Exactly what the learner typed (not cleaned) |
| `grade` | `Grade` | The grader's verdict (correct, matched, typo, expected) |
| `verdict` | `Verdict \| None` | The judge's verdict, or your own mark (source `self`, via `own_mark`); `None` if neither |
| `correct` | `bool` (computed) | Right by the grader, **or** the judge (or your own mark) said yes |

**`QuizResult`**: the whole quiz
| Field | Type | Plain meaning |
|---|---|---|
| `attempts` | `tuple[Attempt, ...]` | Every answer, in the order asked (a tuple, so answers can't be added or removed afterwards) |
| `total` | `int` | How many questions the quiz had (at least 1, and never fewer than `answered` + `skipped`) |
| `skipped` | `int` | How many questions `prepare` skipped (default 0, never negative). They are not answered and not in `attempts` |
| `correct` | `int` (computed) | How many attempts are `correct`. A typo-forgiven or judge-accepted answer **counts as right** |
| `answered` | `int` (computed) | `len(attempts)`, less than `total` if the learner quit early |
| `finished` | `bool` (computed) | `answered + skipped == total` |

Example: quit after 3 of 10 with 2 right → `correct=2, answered=3, total=10, finished=False`. The CLI can then show "2 / 3 (quit early, 7 not asked)". With `prepare`: 10 questions, 2 skipped, 8 answered → `skipped=2, answered=8, finished=True`; the score is out of the 8 answered.

## Tools
- **`quizkit.blocks.grader.grade`**: does all the marking. The engine never compares answers itself.
- **`quizkit.models.Question`**: the input shape.
- **pydantic**: `Attempt`, `QuizResult`.
- **`quizkit.models.Judge` / `Verdict`**: the optional hook's type and result. The engine doesn't import the judge block or any Claude code.
- No files, no network of its own. It never calls Claude itself; a plugged-in judge may. It doesn't import `deck_builder` or anything from `hsk_trainer`.

## Failure modes
| Situation | What it does |
|---|---|
| `questions` is empty | **Raises `ValueError`** when the session is created, so `run_quiz([])` raises before calling `ask` (a quiz with nothing in it is a bug upstream, so it must be loud) |
| `ask` returns `None` (quit) | Stops at once and returns the result so far (`finished=False`). Quitting before question 1 (the first `ask` returns `None`) gives 0 answered, no crash |
| Blank answer `""` | **Not** a quit: the grader marks it wrong and it counts as answered |
| `session.answer()` called after the last question | **Raises `RuntimeError`** (a bug in whatever is calling the engine) |
| `KeyboardInterrupt` (Ctrl-C) raised anywhere in `run_quiz`'s loop: in `ask`, while grading, or in `tell` | **A quit:** `run_quiz` stops and returns the result so far (`finished=False`). An answer already marked counts (even if `tell` was interrupted while showing it); an answer interrupted while being marked doesn't. `ask`/`tell` are not called again |
| `KeyboardInterrupt` while the session is being **created** (before the loop, e.g. during the up-front check) | Passed through: the quiz hasn't started, so there is no score to keep |
| `KeyboardInterrupt` (Ctrl-C) while the **judge** is being asked (e.g. waiting on "asking the judge…") | **A quit**, like Ctrl-C while marking: the result so far is returned and the answer being judged doesn't count |
| The judge raises anything else (e.g. `ValueError`) | Passed through, not swallowed (a bug must be loud). `ClaudeJudge` itself turns Claude problems into a "couldn't check" verdict, so this means a broken judge |
| The grader raises mid-quiz (anything but Ctrl-C) | Passed through, not swallowed (a bug must be loud), and `run_quiz` returns nothing |
| `ask` or `tell` raises anything else (e.g. `ValueError`) | Passed through, not swallowed (a bug must be loud), and `run_quiz` returns nothing |
| `QuizSession` (the brain) and Ctrl-C | Not its job: the brain has no loop, so whoever drives it step by step handles Ctrl-C |
| A card nobody can answer | Found **when the session is created**, before question 1 (each question is graded once with a blank answer), so the grader's error is raised before `ask` is called and no answers are lost mid-quiz. A data bug must be loud, as in the grader's SPEC |
| `prepare` returns `None` | That question is skipped: `skipped` goes up by 1, nothing is asked or graded, and the next question is prepared. If every remaining question is skipped, the quiz is finished (`current` is `None`) |
| `prepare` returns something that isn't a `Question` (or `None`), a question for another `card_id`, or one nobody can answer | **Raises `ValueError`** (the grader's own error, for an unanswerable one) when `current` is read (a bug in `prepare` must be loud). The answers already given are kept in the session |
| `prepare` raises anything (but Ctrl-C) | Passed through, not swallowed |
| `KeyboardInterrupt` (Ctrl-C) inside `prepare` in `run_quiz` (e.g. while waiting for a live sentence) | **A quit**, like Ctrl-C in `ask`: the result so far is returned; the question being prepared isn't skipped or answered |
| Reading `current` again before answering | `prepare` is **not** called again: the prepared question is kept until it is answered (`prepare` may be slow or have side effects) |
| The same question appears twice | Asked twice, both recorded (removing repeats is `deck_builder`'s job) |
| A `QuizResult` built by hand with `total` < 1 or more attempts than `total` | pydantic **rejects** it (`ValidationError`), so a result is trustworthy outside `QuizSession` too (e.g. M5's progress store) |
| The caller changes its `questions` list, or a question's answers, after starting | No effect: the session keeps its own deep copy |
| `own_mark()` before any answer (also when the questions so far were all skipped) | **Raises `RuntimeError`** (nothing to mark) |
| `own_mark()` after a blank or spaces-only answer | **Raises `ValueError`** (nothing was typed to mark) |
| `own_mark()` when the last answer was right by the answer list, or already has a verdict that was checked (Claude, the cache, or your own mark) | **Raises `ValueError`**: only an answer nobody checked (no verdict, or "couldn't check") can take your mark, and only once. `can_own_mark` says so in advance |
| `own_mark()` with something that isn't a `Verdict` | **Raises `TypeError`** |
| `own_mark(verdict, card_id=...)` when the last answer is for another card | **Raises `ValueError`** (the mark was meant for an earlier question) |
| `own_mark()` with a verdict whose `source` isn't `"self"` | **Raises `ValueError`** (it's for your own mark; a judge's verdict comes through `judge`) |
| `own_mark()` after the last question | Allowed: the last answer can still take your mark, and `result()` includes it |

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
- **Judge hook:** not called when the grader says right (exact or typo-forgiven) or for a blank / spaces-only answer; called with the question and the raw typed text when the grader says wrong; a "yes" makes `Attempt.correct` and the score count it (`grade.correct` stays False); a "no" stays wrong; no judge = old behaviour (`verdict` is None); works through `QuizSession` too; Ctrl-C inside the judge → a quit, that answer not counted; any other judge error passed through
- **Prepare hook:** called once per question, in order, with the question as given, and only when it becomes current (not all up front; not again on a second read of `current`); the prepared question is what `ask`, the grader, the judge and the `Attempt` see; `None` skips it (`skipped` counted, `ask` not called for it, `finished` still True at the end); skipping the last questions finishes the quiz; another `card_id` or an unanswerable prepared question → `ValueError`; Ctrl-C inside `prepare` in `run_quiz` → a quit; any other error passed through; no `prepare` = old behaviour (`skipped=0`); works through `QuizSession` too; a hand-built `QuizResult` with `answered + skipped > total` or `skipped < 0` is rejected
- **Own mark:** after a wrong answer with no judge, `can_own_mark` is True and `own_mark(self "yes")` makes it count (`Attempt.correct`, the score, `result()`), returning the new `Attempt`; a self "no" stays wrong but is marked; works after a "couldn't check" verdict; works on the last question; `can_own_mark` False and `own_mark` raises: before any answer (`RuntimeError`), after a right answer, after a checked verdict (Claude, cache, or an own mark already), and for a verdict that isn't `"self"` (`ValueError`); something that isn't a `Verdict` → `TypeError`; a `card_id` for another card → `ValueError` (the right `card_id` works); only the last answer changes
- **Errors:** empty list → `ValueError`; any other error from `ask`, `tell` or the grader is passed through
- **Own copy:** changing the list, or a question's answers, after starting has no effect
- **Bad card found early:** an unanswerable question 2 raises before `ask` is ever called
- **Result can't change:** `attempts` can't be appended to; a hand-built `QuizResult` with bad numbers is rejected
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

Manual check: none here. The real feel is checked in the M3 Step 6 play-test, through the CLI.
