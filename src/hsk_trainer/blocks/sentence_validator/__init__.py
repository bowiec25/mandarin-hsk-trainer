"""sentence_validator: Check one example sentence for a word: the word is in it, a learner at the word's band could read every other word, and it is short; give reasons for any failure.

See SPEC.md in this folder (ADR 0003) and ADR 0008. A script: every rule is checkable
by code. Its reasons are plain English, so sentence_writer can send them back to Claude.
"""

import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quizkit.blocks.base import BlockSpec
from quizkit.models import Card

BLOCK_SPEC = BlockSpec(
    name="sentence_validator",
    kind="script",
    goal="Check one example sentence for a word: the word is in it, a learner at the word's band could read every other word, and it is short; give reasons for any failure.",
    inputs=["vocab", "sentence", "word", "settings"],
    outputs=["SentenceCheck"],
)

# Chinese characters: 〇, Ext-A, the main block, compatibility, and Ext-B onwards.
_HANZI_RANGES = "\u3007\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af"
_HANZI = re.compile(f"[{_HANZI_RANGES}]")
# Chinese text uses these as punctuation, but Unicode calls them symbols.
_ALSO_PUNCTUATION = set("·～")


def _is_hanzi(ch: str) -> bool:
    return bool(_HANZI.fullmatch(ch))


def _is_chinese_punctuation(ch: str) -> bool:
    """Any non-ASCII punctuation mark (，。《》『』…), plus · and ～."""
    if ch in _ALSO_PUNCTUATION:
        return True
    return ord(ch) > 127 and unicodedata.category(ch).startswith("P")


class SentenceSettings(BaseModel):
    """How long a sentence may be, and words that are always allowed."""

    model_config = ConfigDict(frozen=True)

    min_chars: int = Field(
        default=3, ge=1
    )  # Chinese characters; punctuation not counted
    max_chars: int = 20
    extra_words: tuple[str, ...] = ()

    @model_validator(mode="after")
    def max_not_below_min(self) -> "SentenceSettings":
        if self.max_chars < self.min_chars:
            raise ValueError(
                f"max_chars ({self.max_chars}) is below min_chars ({self.min_chars})"
            )
        return self


class SentenceCheck(BaseModel):
    """The verdict on one sentence: passed, why not, and the reading it chose."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    reasons: tuple[str, ...]
    words: tuple[str, ...]


class Vocab:
    """Every HSK word and its band."""

    def __init__(self, cards: list[Card]) -> None:
        if not cards:
            raise ValueError("Vocab needs at least one card")
        self.levels: dict[str, int] = {}
        for card in cards:
            hanzi = card.fields["hanzi"]
            if hanzi in self.levels:
                raise ValueError(f"two cards share the hanzi {hanzi!r}")
            self.levels[hanzi] = card.level
        self.longest = max(len(w) for w in self.levels)


def _bands(band: int) -> str:
    return "band 1" if band == 1 else f"bands 1–{band}"


# A reading so far: (problems, pieces, words, reasons). Fewer problems, then fewer
# pieces, is better.
_Reading = tuple[int, int, tuple[str, ...], tuple[str, ...]]


def _read(
    text: str,
    word: str,
    band: int,
    vocab: Vocab,
    extras: frozenset[str],
    word_on_its_own: bool,
) -> _Reading | None:
    """The best reading of `text` as a row of words (dynamic programming).

    Pieces are HSK words, extra words, single unknown characters, or `word` itself
    (matched as written). Anything that isn't a Chinese character is skipped for free
    (rule 1 reports it). With `word_on_its_own`, only readings that use `word` count.
    """
    longest = max([vocab.longest, *(len(e) for e in extras)])
    n = len(text)
    # best[i][used]: the best reading of text[:i]; used = `word` is one of its pieces
    best: list[list[_Reading | None]] = [[None, None] for _ in range(n + 1)]
    best[0][0] = (0, 0, (), ())

    def offer(end: int, used: int, reading: _Reading) -> None:
        current = best[end][used]
        if current is None or reading[:2] < current[:2]:
            best[end][used] = reading

    for i in range(n):
        for used in (0, 1):
            here = best[i][used]
            if here is None:
                continue
            problems, pieces, words, reasons = here
            if text.startswith(word, i):
                offer(i + len(word), 1, (problems, pieces + 1, (*words, word), reasons))
            if not _is_hanzi(text[i]):
                offer(i + 1, used, here)  # punctuation etc.: skipped, no cost
                continue
            for end in range(i + 1, min(n, i + longest) + 1):
                piece = text[i:end]
                if not _is_hanzi(piece[-1]):
                    break  # a word never runs across punctuation
                if piece == word:
                    continue  # offered above
                if piece in extras:
                    problem = None
                elif piece in vocab.levels:
                    level = vocab.levels[piece]
                    problem = (
                        None
                        if level <= band
                        else f"uses {piece} (band {level}); a sentence for a "
                        f"band-{band} word may only use {_bands(band)}"
                    )
                elif end == i + 1:
                    problem = f"uses {piece}, not an HSK word in {_bands(band)}"
                else:
                    continue  # not a word: only single characters may be unknown
                offer(
                    end,
                    used,
                    (
                        problems + (problem is not None),
                        pieces + 1,
                        (*words, piece),
                        (*reasons, problem) if problem else reasons,
                    ),
                )
    ends = [best[n][1]] if word_on_its_own else [best[n][0], best[n][1]]
    found = [r for r in ends if r is not None]
    return min(found, key=lambda r: r[:2]) if found else None


def check_sentence(
    sentence: str,
    word: str,
    vocab: Vocab,
    settings: SentenceSettings | None = None,
) -> SentenceCheck:
    """Check `sentence` for `word` against every rule; report all problems."""
    settings = settings or SentenceSettings()
    if word not in vocab.levels:
        raise ValueError(f"{word!r} is not one of the cards")
    band = vocab.levels[word]
    text = sentence.strip()
    if not text:
        return SentenceCheck(passed=False, reasons=("empty sentence",), words=())

    reasons: list[str] = []
    # 1. Only Chinese characters and Chinese punctuation.
    outside_word = text.replace(word, "")  # a card word like T恤 may have a letter
    others = sorted(
        {c for c in outside_word if not _is_hanzi(c) and not _is_chinese_punctuation(c)}
    )
    if others:
        shown = " ".join(repr(c) for c in others)
        reasons.append(f"has characters that aren't Chinese: {shown}")
    # 2. The word is in it.
    present = word in text
    if not present:
        reasons.append(f"doesn't contain {word}")
    # 3. Length, in Chinese characters.
    count = sum(_is_hanzi(c) for c in text)
    if count < settings.min_chars:
        reasons.append(
            f"too short: {count} Chinese characters (min {settings.min_chars})"
        )
    if count > settings.max_chars:
        reasons.append(
            f"too long: {count} Chinese characters (max {settings.max_chars})"
        )
    # 4. Readable at this band (checked even when the word is missing, so Claude
    #    hears about every problem at once).
    extras = frozenset(settings.extra_words)
    free = _read(text, word, band, vocab, extras, word_on_its_own=False)
    reading = free
    note = None
    if present:
        alone = _read(text, word, band, vocab, extras, word_on_its_own=True)
        inside = [w for w in (free[2] if free else ()) if word in w and w != word]
        if alone is not None and free is not None and alone[0] > free[0] and inside:
            note = f"has {word} only inside {inside[0]}, not on its own"
        else:
            reading = alone
    if reading is not None:
        reasons.extend(reading[3])
        words = reading[2]
    else:
        words = ()
    if note:
        reasons.append(note)

    unique = tuple(dict.fromkeys(reasons))  # a word used twice is reported once
    return SentenceCheck(passed=not unique, reasons=unique, words=words)
