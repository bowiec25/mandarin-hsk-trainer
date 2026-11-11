"""The web app (ADR 0014): `uv run hsk web` opens it in your browser.

The entry only: the page settings and Streamlit's page menu (Quiz, Stats). The pages
live in `web_pages/`. Switching page keeps a running quiz (same browser tab).
It runs on your computer only (localhost); nothing is sent to Streamlit.
"""

from pathlib import Path

import streamlit as st

PAGES = Path(__file__).with_name("web_pages")
# Settings that must survive a page switch: Streamlit forgets a widget's value on a
# run where it isn't drawn, unless it's set again here (its documented way).
KEPT = ("band", "mode", "n", "judge", "live", "save", "stats_band")

st.set_page_config(page_title="HSK Trainer", page_icon="📚")
for key in KEPT:
    if key in st.session_state:
        st.session_state[key] = st.session_state[key]
st.navigation(
    [
        st.Page(PAGES / "quiz.py", title="Quiz", icon="📝", default=True),
        st.Page(PAGES / "stats.py", title="Stats", icon="📊"),
    ]
).run()
