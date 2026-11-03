"""sentence_validator: Check one example sentence for a word: the word is in it, every other word is at or below the word's band, and it is short; give reasons for any failure.

See SPEC.md in this folder (ADR 0003) and ADR 0008. A script: every rule is checkable
by code. Its reasons are plain English, so sentence_writer can send them back to Claude.
"""

import logging
import re

import jieba
from pydantic import BaseModel, ConfigDict, Field, model_validator

from quizkit.blocks.base import BlockSpec
from quizkit.models import Card

BLOCK_SPEC = BlockSpec(
    name="sentence_validator",
    kind="script",
    goal="Check one example sentence for a word: the word is in it, every other word is at or below the word's band, and it is short; give reasons for any failure.",
    inputs=["cards", "sentence", "word", "settings"],
    outputs=["SentenceCheck"],
)

PUNCTUATION = "，。？！、：；“”‘’"
_HANZI = re.compile(r"[㐀-䶿一-鿿豈-﫿]")  # Chinese characters

jieba.setLogLevel(logging.WARNING)  # no "Building prefix dict..." chatter


def _is_hanzi(ch: str) -> bool:
    return bool(_HANZI.fullmatch(ch))


class SentenceSettings(BaseModel):
    """How long a sentence may be, and words that are always allowed."""

    model_config = ConfigDict(frozen=True)

    min_chars: int = Field(
        default=4, ge=1
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
    """The verdict on one sentence: passed, why not, and the words it checked."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    reasons: tuple[str, ...]
    words: tuple[str, ...]


class Vocab:
    """Every HSK word and its band, plus a jieba splitter that knows all of them."""

    def __init__(self, cards: list[Card]) -> None:
        if not cards:
            raise ValueError("Vocab needs at least one card")
        self.levels: dict[str, int] = {}
        for card in cards:
            hanzi = card.fields["hanzi"]
            if hanzi in self.levels:
                raise ValueError(f"two cards share the hanzi {hanzi!r}")
            self.levels[hanzi] = card.level
        self._longest = max(len(w) for w in self.levels)
        # Its own Tokenizer, so the global jieba (and any other user of it) is untouched.
        self._jieba = jieba.Tokenizer()
        for word in self.levels:
            self._jieba.add_word(word)

    def pieces(self, text: str) -> list[str]:
        """jieba's split of `text`, keeping only pieces with Chinese characters."""
        return [p for p in self._jieba.lcut(text) if any(_is_hanzi(c) for c in p)]

    def split_into(self, piece: str, allowed: set[str]) -> list[str] | None:
        """Split `piece` completely into `allowed` words (fewest pieces), or None."""
        longest = max(self._longest, *(len(w) for w in allowed)) if allowed else 0
        best: list[list[str] | None] = [[]] + [None] * len(piece)
        for end in range(1, len(piece) + 1):
            for start in range(max(0, end - longest), end):
                head = best[start]
                if head is not None and piece[start:end] in allowed:
                    candidate = [*head, piece[start:end]]
                    current = best[end]
                    if current is None or len(candidate) < len(current):
                        best[end] = candidate
        return best[len(piece)]


def _bands(band: int) -> str:
    return "band 1" if band == 1 else f"bands 1–{band}"


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
    others = sorted({c for c in text if not _is_hanzi(c) and c not in PUNCTUATION})
    if others:
        shown = " ".join(repr(c) for c in others)
        reasons.append(f"has characters that aren't Chinese: {shown}")
    # 2. The word is in it.
    if word not in text:
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
    # 4. Every other word is allowed for this band.
    extras = set(settings.extra_words)
    allowed = {w for w, b in vocab.levels.items() if b <= band} | extras
    words: list[str] = []
    for piece in vocab.pieces(text):
        if piece in vocab.levels:
            words.append(piece)
            if vocab.levels[piece] > band:
                reasons.append(
                    f"uses {piece} (band {vocab.levels[piece]}); a sentence for a "
                    f"band-{band} word may only use {_bands(band)}"
                )
        elif piece in extras:
            words.append(piece)
        elif (parts := vocab.split_into(piece, allowed)) is not None:
            words.extend(parts)  # glued words, e.g. 吃饭 -> 吃 + 饭
        else:
            words.append(piece)
            reasons.append(f"uses {piece}, not an HSK word in {_bands(band)}")

    unique = tuple(dict.fromkeys(reasons))  # a word used twice is reported once
    return SentenceCheck(passed=not unique, reasons=unique, words=tuple(words))
