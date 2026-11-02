"""cedict_cleaner: Turn one CC-CEDICT dictionary meaning into zero or more answers a
learner could type.

See SPEC.md in this folder (ADR 0003). This is the HSK `cleaner` passed to the generic
grader: `grade(answer, card.answers, cleaner=clean_answer)`.
"""

import re

from quizkit.blocks.base import BlockSpec

BLOCK_SPEC = BlockSpec(
    name="cedict_cleaner",
    kind="script",
    goal="Turn one CC-CEDICT dictionary meaning into zero or more answers a learner could type.",
    inputs=["meaning: str"],
    outputs=["list[str]"],
)

HANZI = re.compile(r"[㐀-鿿]")

# Rule 1: meanings that aren't the HSK meaning.
_DROP = re.compile(
    r"^(surname\b|abbr\.|also written\b|also pr\.|taiwan pr\.)"
    r"|variant of\b"
    rf"|^(see|used in)\s*{HANZI.pattern}",
    re.IGNORECASE,
)
# Rule 2: innermost (...) or [...] notes, removed one layer at a time.
_NOTE = re.compile(r"\(([^()\[\]]*)\)|\[[^()\[\]]*\]")
# Rule 3: notes that are labels, not part of the meaning.
_LABELS = {
    "abbr", "archaic", "coll", "dialect", "esp", "fig", "formal", "honorific",
    "informal", "lit", "literary", "loanword", "math", "old", "onom", "pejorative",
    "polite", "prefix", "sb", "slang", "sth", "suffix", "tw",
}  # fmt: skip
_PLAIN_WORD = re.compile(r"[A-Za-z]+")
# Rule 4: placeholder words and dots.
_PLACEHOLDER = re.compile(r"\b(sb|sth)('s)?\b|\betc\b\.?|\.\.\.|…")  # "sb's" too
_CLASSIFIER = re.compile(r"^classifier for\s+", re.IGNORECASE)


def _tidy(text: str) -> str:
    """Drop stray brackets, collapse spaces, no space before punctuation, no
    dangling commas/colons at the ends."""
    text = re.sub(r"[()\[\]]", " ", text)
    text = " ".join(text.split())
    text = re.sub(r"\s+([,;:.?!])", r"\1", text)
    return text.strip(" ,;:")


def _without_notes(meaning: str, keep_plain_words: bool) -> str:
    """Remove (...) and [...] notes (rule 2), optionally unwrapping one-plain-word
    notes instead (rule 3)."""

    def replace(match: re.Match[str]) -> str:
        word = match.group(1)
        if (
            keep_plain_words
            and word
            and _PLAIN_WORD.fullmatch(word)
            and word.casefold() not in _LABELS
        ):
            return word
        return " "

    previous = None
    while previous != meaning:
        previous, meaning = meaning, _NOTE.sub(replace, meaning)
    return _tidy(_PLACEHOLDER.sub(" ", meaning))


def _items(text: str) -> list[str]:
    return [_tidy(item) for item in text.split(",")]


def _keep(results: list[str]) -> list[str]:
    """Rule 8: no Chinese, no blanks, no duplicates (first seen wins)."""
    kept: list[str] = []
    for r in results:
        if r and not HANZI.search(r) and r not in kept:
            kept.append(r)
    return kept


def clean_answer(meaning: str) -> list[str]:
    """Turn one dictionary meaning into the answers a learner could type (SPEC.md)."""
    meaning = meaning.strip()
    if not meaning or _DROP.search(meaning):
        return []

    main = _without_notes(meaning, keep_plain_words=False)
    if not main:
        return []

    # Rules 5 and 6: colon lists, then classifiers, replace the meaning.
    if ":" in main:
        listed = _keep(_items(main.rsplit(":", 1)[1]))
        if listed:
            return listed
    elif _CLASSIFIER.match(main):
        listed = _keep(_items(_CLASSIFIER.sub("", main)))
        if listed:
            return listed

    results = [main, _without_notes(meaning, keep_plain_words=True)]  # rule 3
    if "," in main:
        results.append(_tidy(main.split(",", 1)[0]))  # rule 7
    return _keep(results)
