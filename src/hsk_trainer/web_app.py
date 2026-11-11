"""The web app (ADR 0014): `uv run hsk web` opens it in your browser.

The entry only: the page settings and Streamlit's page menu (Quiz, Stats). The pages
live in `web_pages/`. Switching page keeps a running quiz (same browser tab).
It runs on your computer only (localhost); nothing is sent to Streamlit.
"""

from pathlib import Path

import streamlit as st

PAGES = Path(__file__).with_name("web_pages")

st.set_page_config(page_title="HSK Trainer", page_icon="📚")
st.navigation(
    [
        st.Page(PAGES / "quiz.py", title="Quiz", icon="📝", default=True),
        st.Page(PAGES / "stats.py", title="Stats", icon="📊"),
    ]
).run()
