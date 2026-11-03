"""sentence_validator: Check one example sentence for a word: the word is in it, every other word is at or below the word's band, and it is short; give reasons for any failure.

See SPEC.md in this folder (ADR 0003) and ADR 0008. A script: every rule is checkable
by code. Its reasons are plain English, so sentence_writer can send them back to Claude.
"""

import re

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

PUNCTUATION = set("，。？！、：；“”‘’…—《》（）·～「」")
# Chinese characters: 〇, Ext-A, the main block, compatibility, and Ext-B onwards.
_HANZI = re.compile(
    "[\u3007\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]"
)


def _is_hanzi(ch: str) -> bool:
    return bool(_HANZI.fullmatch(ch))


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


def _best_reading(
    run: str, word: str, band: int, vocab: Vocab, extras: frozenset[str]
) -> list[tuple[int, int, list[str], list[str], bool]]:
    """Best readings of one run of Chinese characters, for both "word used" states.

    Returns, for start state used=False and used=True, the best (problems, pieces,
    words, reasons, used_at_end). A reading is a row of pieces: HSK words, extra words,
    or single unknown characters. Fewest problems wins, then fewest pieces.
    """
    longest = (
        max(vocab.longest, len(word), *(len(e) for e in extras))
        if extras
        else max(vocab.longest, len(word))
    )
    results = []
    for start_used in (False, True):
        # best[i][u] = (problems, pieces, words, reasons) for run[:i], word used = u
        best: list[list[tuple | None]] = [[None, None] for _ in range(len(run) + 1)]
        best[0][int(start_used)] = (0, 0, [], [])
        for i in range(len(run)):
            for used in (0, 1):
                here = best[i][used]
                if here is None:
                    continue
                for end in range(i + 1, min(len(run), i + longest) + 1):
                    piece = run[i:end]
                    now_used = used
                    if piece == word:
                        problem, now_used = None, 1
                    elif piece in extras:
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
                    candidate = (
                        here[0] + (problem is not None),
                        here[1] + 1,
                        [*here[2], piece],
                        [*here[3], problem] if problem else here[3],
                    )
                    current = best[end][now_used]
                    if current is None or candidate[:2] < current[:2]:
                        best[end][now_used] = candidate
        results.append(best[len(run)])
    return results


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
    # 4. Readable at this band: the reading with the fewest problems, word on its own.
    words: list[str] = []
    if present:
        extras = frozenset(settings.extra_words)
        runs = [r for r in re.split(f"[^{_HANZI.pattern[1:-1]}]+", text) if r]
        # Chain the runs, carrying "word used yet?" from one run to the next.
        state: dict[bool, tuple[int, int, list[str], list[str]]] = {
            False: (0, 0, [], [])
        }
        for run in runs:
            per_start = _best_reading(run, word, band, vocab, extras)
            nxt: dict[bool, tuple[int, int, list[str], list[str]]] = {}
            for used_before, (p, n, ws, rs) in state.items():
                for used_after, found in enumerate(per_start[int(used_before)]):
                    if found is None:
                        continue
                    total = (p + found[0], n + found[1], ws + found[2], rs + found[3])
                    old = nxt.get(bool(used_after))
                    if old is None or total[:2] < old[:2]:
                        nxt[bool(used_after)] = total
            state = nxt
        _, _, words, problems = state[True]  # the word is present, so this exists
        reasons.extend(problems)

    unique = tuple(dict.fromkeys(reasons))  # a word used twice is reported once
    return SentenceCheck(passed=not unique, reasons=unique, words=tuple(words))
