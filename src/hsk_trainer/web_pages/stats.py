"""The web Stats page (ADR 0014): the same numbers as `hsk stats`.

Read-only: it never makes the progress file. The numbers come from
`quiz_setup.gather_stats` (shared with `hsk stats`), so the two always agree.
"""

import pandas as pd
import streamlit as st

from hsk_trainer.quiz_setup import (
    QuizFiles,
    SetupError,
    box_counts,
    gather_stats,
    nothing_yet,
    week_line,
    week_pct,
)
from hsk_trainer.web_pages import safe

BAR_COLOUR = "#2a78d6"  # one series, one hue (the dataviz palette's first slot)
NO_PROGRESS = (
    "No progress saved yet: play a quiz on the Quiz page "
    "(it saves unless you untick Save progress)."
)

st.title("📊 Stats")
choice = st.selectbox("Band", ["All", 1, 2, 3], key="stats_band")
# The quiz's own files if a quiz was set up (one source of truth); tests may put
# their own; else the defaults (your progress file).
quiz = st.session_state.get("quiz")
files = (
    st.session_state.get("stats_files") or getattr(quiz, "files", None) or QuizFiles()
)
try:
    report = gather_stats(files, None if choice == "All" else choice)
except SetupError as err:
    st.error(safe("\n\n".join(err.lines)))
    st.stop()
if report is None:
    st.info(NO_PROGRESS)
    st.stop()

for band in report:
    st.header(f"Band {band.band} · {band.words} words")
    for part in band.skills:
        s = part.stats
        st.subheader(f"{part.skill} ({', '.join(part.modes)})")
        if nothing_yet(s):
            st.caption("Nothing yet.")
            continue
        new, due, week = st.columns(3)
        new.metric("New", s.new, help="Words never answered for this skill")
        due.metric("Due now", s.due, help="Words whose wait is over: asked first")
        pct = week_pct(s)
        week.metric("Last 7 days", "–" if pct is None else f"{pct}%")
        st.caption(safe(f"Last 7 days: {week_line(s)}"))
        boxes = box_counts(s)
        st.caption("Words per box (box 1 = asked most often)")
        st.bar_chart(
            pd.DataFrame(
                {"Box": [b for b, _ in boxes], "Words": [n for _, n in boxes]}
            ),
            x="Box",
            y="Words",
            color=BAR_COLOUR,
            height=220,
        )
        st.caption(safe(" · ".join(f"box {b}: {n}" for b, n in boxes)))
        if s.most_missed:
            st.caption("Most missed")
            st.dataframe(
                pd.DataFrame(
                    {
                        "Word": [band.label.get(c, c) for c, _ in s.most_missed],
                        "Missed": [n for _, n in s.most_missed],
                    }
                ),
                hide_index=True,
            )
