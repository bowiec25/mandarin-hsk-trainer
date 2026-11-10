# 0014: A Streamlit web quiz on a shared HSK setup

- **Status:** Accepted (2026-11-10)
- **In plain words:** M6 adds a web page for the quiz, built with Streamlit. It runs on your computer and opens in your browser. Before building it, the HSK setup moves out of the terminal program into one shared file, so the terminal and the web page drive the same blocks and nothing is copied. The first version has the quiz (all 6 modes, saving, due words first) and a stats page (your choice).

## Context
- The plan (M6) said: "a Streamlit front end on the same `quizkit` engine, with no logic duplicated".
- What we found when checking it against the code (the M4–M5 lesson: check a block's inputs and timing, not just its features):
  - **The engine is ready.** `QuizSession` works one step at a time: `current` (the question now, prepared), `answer(typed)` (mark it), `done`, `result()`. A web page needs exactly that. `run_quiz` is the terminal's loop around it.
  - **The HSK setup lives in `cli.py`** (649 lines): which card fields each mode shows, the sentence part (bank + live sentences, `prepare` for translate), which judge and rubric, typo settings, saving (`_Saving`), the box line. A web page would have to copy all of it.
  - **Self-marking pauses inside marking.** In translate modes without Claude, "Did you get the gist? (y/n)" is asked *inside* the judge call, in the middle of `answer()`. A terminal can wait there; a web page can't (each click is a new run of the page).
  - **Slow steps:** the judge (~8 s) and a live sentence (up to 15 s) block while they run.
  - **Streamlit reruns the page script on every click.** Anything that must last (the session, the store, the sentence threads) is kept in `st.session_state`.

## Decision
1. **Streamlit, local only.** `uv run hsk web` starts it (`streamlit run`) and it opens in your browser. Not hosted: your files stay on your computer. Streamlit is added with `uv add streamlit`.
2. **One shared HSK setup: `src/hsk_trainer/quiz_setup.py`** (glue, like `cli.py`, not a block). From the quiz options (band, mode, n, seed, judge on/off, live on/off, save on/off) it builds what a quiz needs:
   - the deck (due words first),
   - the grading settings,
   - the judge (word rubric or gist rubric),
   - the sentence part and `prepare`,
   - the saver,
   - the end-of-quiz summary.

   The terminal and the web page both call it. Moving it is **its own PR with no behaviour change**: the existing CLI tests must pass unchanged.
3. **Engine: your own mark after an answer.** `QuizSession` gets a method to record **your own mark on the last answer**, allowed only when the answer list said wrong and nobody checked it (no verdict, or "couldn't check"). It returns the updated `Attempt` (verdict source `self`). The web page uses it: answer → if it needs your mark, show "Did you get the gist?" → your mark → save. The terminal keeps its prompt inside the judge (it works there). Both use the same wording and the same verdicts, from the shared setup.
4. **Saving happens once an answer is final**: after the grader, the judge and (if asked) your own mark. The same `quizkit.progress.save_attempt`, the same `data/progress.db`.
5. **Pages:**
   - **Quiz:** choose band, mode, how many, and the switches (judge, live sentences, save). Then one question at a time: the word or sentence, an answer box, the result (✅/❌, the accepted answers or the judge's reason, then the sentence or the word after a translation), and **Next**. The end shows the score and the box line.
   - **Stats:** the same numbers as `hsk stats`, from `quizkit.progress.skill_stats`.
6. **Slow steps show a spinner** ("asking the judge…", "writing a sentence…"). One person and one browser tab at a time, the same as the terminal.
7. **Tests:** the shared setup gets its own tests; the pages are tested with Streamlit's built-in `AppTest` (it runs a page in the test, with no browser), with a fake Claude, as everywhere else.

## PR plan (small PRs)
1. This ADR.
2. Shared HSK setup out of `cli.py` (no behaviour change).
3. Engine: your own mark after an answer (block change: test-writer → build → block-reviewer).
4. Web quiz page + `hsk web`.
5. Stats page.
6. Docs + M6 lessons + build map; data-auditor at the milestone end.

## Why / alternatives considered
- **NiceGUI or FastAPI + HTMX:** more control over the page and no reruns, but more code and (for HTMX) HTML templates. Streamlit is the quickest way to a usable page in plain Python, and the plan already chose it.
- **A terminal UI (Textual):** nicer than the plain terminal, but it's not a web page.
- **Copy the setup into the web page:** fastest today, but every later change would have to be made twice. "No logic duplicated" was the M6 goal from the start.
- **Self-marking inside the judge for the web too:** impossible: Streamlit can't pause in the middle of `answer()`.
