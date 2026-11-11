"""The web quiz page (ADR 0014): `uv run hsk web` opens it in your browser.

Thin on purpose: Streamlit reruns this whole script on every click, so it only
(1) passes the click to the quiz's brain (`WebQuiz`, kept in session state) and
(2) draws what the brain says. Slow steps (the judge, a new sentence) get a spinner.
It runs on your computer only (localhost); nothing is sent to Streamlit.
"""

import re

import streamlit as st

from hsk_trainer.quiz_setup import PLAYABLE_MODES, QuizOptions
from hsk_trainer.web_quiz import WebQuiz

st.set_page_config(page_title="HSK Trainer", page_icon="📚")

if "quiz" not in st.session_state:  # a test may put its own (fake judge) here first
    st.session_state["quiz"] = WebQuiz()
quiz: WebQuiz = st.session_state["quiz"]
running = quiz.phase in ("asking", "own_mark", "result")


_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!|~$<>])")  # each gets a backslash


def _safe(text: str) -> str:
    """Data (sentences, answers, reasons, paths) shown as written: Streamlit reads
    text as Markdown and maths, so "$5" or a Windows path would be mangled."""
    return _MARKDOWN.sub(r"\\\1", text)


def _lines(lines: list[str]) -> None:
    for line in lines:
        st.caption(_safe(line))


# --- Settings (locked while a quiz runs) -------------------------------------------
with st.sidebar:
    st.header("Quiz")
    band = st.selectbox("Band", [1, 2, 3], key="band", disabled=running)
    mode = st.selectbox("Mode", PLAYABLE_MODES, key="mode", disabled=running)
    n = st.number_input(
        "How many", min_value=1, max_value=500, value=10, key="n", disabled=running
    )
    judge = st.checkbox(
        "Claude judge",
        value=True,
        key="judge",
        disabled=running,
        help="Ask Claude about answers the list misses (needs `claude`, online).",
    )
    live = st.checkbox(
        "Live sentences",
        value=True,
        key="live",
        disabled=running,
        help="Sentence modes: new sentences from Claude as you play (online).",
    )
    save = st.checkbox(
        "Save progress",
        value=True,
        key="save",
        disabled=running,
        help="Save your answers and Leitner boxes, and deal due words first.",
    )
    if not running and st.button("Start quiz", type="primary", key="start"):
        options = QuizOptions(
            band=band, mode=mode, n=int(n), judge=judge, live=live, save=save
        )
        with st.spinner("Setting up the quiz…"):
            quiz.start(options)
        st.rerun()
    if running and st.button("Stop quiz", key="stop"):
        with st.spinner("Stopping (saving any sentence still being written)…"):
            quiz.stop()
        st.rerun()

# --- The quiz ----------------------------------------------------------------------
st.title("HSK Trainer")

if quiz.phase == "setup":
    st.write("Choose a band and a mode on the left, then **Start quiz**.")
    for line in quiz.problems:
        st.error(_safe(line))

elif quiz.view is not None and quiz.phase in ("asking", "own_mark", "result"):
    view = quiz.view
    kind = "Sentence" if view.translating else "Word"
    st.subheader(f"{kind} {view.number} of {view.total}")
    _lines(view.intro)
    _lines([f"({note})" for note in view.notes])
    st.markdown(f"## {_safe(view.shown[0])}")
    for extra in view.shown[1:]:  # pinyin, when the mode shows it
        st.markdown(_safe(extra))
    if view.sentence:  # sentence modes: the example under the word
        st.markdown(f"### {_safe(view.sentence[0])}")
        _lines(view.sentence[1:])

    if quiz.phase == "asking":
        with st.form(f"answer-{view.number}", clear_on_submit=True):
            typed = st.text_input(
                "Your answer (in English)",
                key=f"typed-{view.number}",
                autocomplete="off",  # the browser mustn't suggest your old answers
            )
            checked = st.form_submit_button("Check", type="primary")
        if checked:
            with st.spinner("Checking (the Claude judge can take a few seconds)…"):
                quiz.submit(typed, view.card_id)
            st.rerun()

    elif quiz.phase == "own_mark" and quiz.marking is not None:
        mark = quiz.marking
        st.text(f"You wrote: {mark.typed}")
        st.info(_safe(f"= {mark.english}"))
        if mark.why:
            st.caption(f"({mark.why})")
        st.write(f"**{mark.question}** Mark it yourself (Y / N):")
        yes, no = st.columns(2)
        if yes.button("Yes", key=f"yes-{view.number}", width="stretch", shortcut="Y"):
            quiz.mark(True, mark.card_id)
            st.rerun()
        if no.button("No", key=f"no-{view.number}", width="stretch", shortcut="N"):
            quiz.mark(False, mark.card_id)
            st.rerun()

    elif quiz.phase == "result" and quiz.result is not None:
        res = quiz.result
        st.text(f"You wrote: {res.typed}" if res.typed.strip() else "(no answer)")
        # The ✅ / ❌ becomes the box's icon (Streamlit would take it anyway).
        mark, _, rest = res.headline.partition(" ")
        box = st.success if res.right else st.error
        box(_safe(rest) or ("Right" if res.right else "Wrong"), icon=mark)
        _lines(res.details)
        for line in res.after:
            st.markdown(_safe(line))
        if res.warning:
            st.warning(_safe(res.warning))
        if st.button(  # Enter: no typing box on this screen, so it's free
            "Next →", type="primary", key=f"next-{view.number}", shortcut="Enter"
        ):
            with st.spinner("Getting the next question…"):
                quiz.next(res.card_id)
            st.rerun()

elif quiz.phase == "ended":
    st.subheader("Done")
    for line in quiz.summary:
        st.markdown(_safe(line))
    if st.button("New quiz", type="primary", key="new"):
        quiz.new_quiz()
        st.rerun()
