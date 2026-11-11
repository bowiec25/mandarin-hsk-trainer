"""The web app's pages (ADR 0014): `quiz.py` and `stats.py`, run by Streamlit.

`web_app.py` (one folder up) is the entry: the page settings and the page menu.
"""

import re

_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!|~$<>])")  # each gets a backslash


def safe(text: str) -> str:
    """Data (sentences, answers, reasons, paths) shown as written: Streamlit reads
    text as Markdown and maths, so "$5" or a Windows path would be mangled."""
    return _MARKDOWN.sub(r"\\\1", text)
