"""normalizer: Turn the 3 raw HSK word lists (bands 1-3) into one flat file of Card
records, one card per word.

See SPEC.md in this folder (ADR 0003).
Run by hand: uv run python -m hsk_trainer.blocks.normalizer
"""

import json
from pathlib import Path

from pydantic import ValidationError

from quizkit.blocks.base import BlockSpec
from quizkit.files import write_atomically
from quizkit.models import Card

BLOCK_SPEC = BlockSpec(
    name="normalizer",
    kind="script",
    goal="Turn the 3 raw HSK word lists (bands 1-3) into one flat file of Card "
    "records, one card per word",
    inputs=["src: Path", "dest: Path"],
    outputs=["list[Card]"],
)

DEFAULT_SRC = Path("data/raw/hsk3_2026")
DEFAULT_DEST = Path("data/processed/cards.jsonl")
BANDS = (1, 2, 3)
BRACKETS = {"(": ")", "[": "]"}


class NormalizeError(RuntimeError):
    """The raw data is missing or broken; the message names the file (and word/band)."""


def run(src: Path = DEFAULT_SRC, dest: Path = DEFAULT_DEST) -> list[Card]:
    """Read bands 1-3 from `src`, build one Card per word, write them to `dest`.

    Everything is checked before anything is written, so on error nothing changes.
    """
    src, dest = Path(src), Path(dest)
    cards: list[Card] = []
    seen: dict[str, int] = {}  # word -> band it was first seen in
    for band in BANDS:
        file = src / f"{band}.json"
        for raw in _load_words(file):
            card = _to_card(raw, band, file)
            if card.id in seen:
                raise NormalizeError(
                    f"{file.name}: word {card.id!r} (band {band}) already appears "
                    f"in band {seen[card.id]}"
                )
            seen[card.id] = band
            cards.append(card)

    lines = "".join(
        json.dumps(c.model_dump(), ensure_ascii=False) + "\n" for c in cards
    )
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_atomically(dest, lines.encode("utf-8"))
    except OSError as err:  # disk full, no permission...
        raise NormalizeError(f"{dest.name}: could not save ({err})") from err
    return cards


def _load_words(file: Path) -> list:
    try:
        words = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise NormalizeError(f"{file.name}: raw file is missing ({file})") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise NormalizeError(f"{file.name}: not valid JSON ({err})") from None
    if not isinstance(words, list) or not all(isinstance(w, dict) for w in words):
        raise NormalizeError(f"{file.name}: expected a list of words")
    return words


def _to_card(raw: dict, band: int, file: Path) -> Card:
    simplified = raw.get("simplified")
    hanzi = simplified.strip() if isinstance(simplified, str) else ""

    def fail(problem: str) -> NormalizeError:
        return NormalizeError(f"{file.name}: word {hanzi!r} (band {band}) {problem}")

    if not hanzi:
        raise fail("has no characters")
    forms = raw.get("forms")
    if not forms:
        raise fail("has no readings")
    pos = raw.get("pos")  # must be a list; may be empty (11 real words have none)
    if not isinstance(forms, list) or not _is_str_list(pos):
        raise fail("is malformed (forms must be a list, pos a list of text)")

    readings: list[str] = []
    answers: list[str] = []
    for form in forms:
        pinyin = _get(form, "transcriptions", "pinyin")
        meanings = _get(form, "meanings")
        if not isinstance(pinyin, str) or not _is_str_list(meanings):
            raise fail(
                "has a malformed reading (pinyin must be text, meanings a list of text)"
            )
        if not pinyin.strip():
            raise fail("has a reading with blank pinyin")
        if pinyin.strip() not in readings:
            readings.append(pinyin.strip())
        for meaning in meanings:
            for part in split_meaning(meaning):
                if part not in answers:
                    answers.append(part)
    if not answers:
        raise fail("has no meanings")

    fields = {
        "hanzi": hanzi,
        "pinyin": " / ".join(readings),
        "pos": ", ".join(pos),
        "readings": str(len(readings)),
    }
    try:
        return Card(id=hanzi, fields=fields, answers=answers, level=band)
    except ValidationError as err:
        raise fail(f"can't become a card ({err})") from None


def _get(obj: object, *keys: str) -> object:
    """Follow nested keys, or return None if any step isn't a dict / key is missing."""
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _is_str_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def split_meaning(text: str) -> list[str]:
    """Split at ';' (not inside () or []), trim, drop blanks."""
    parts, current, closers = [], [], []
    for ch in text:
        if ch in BRACKETS:
            closers.append(BRACKETS[ch])
        elif closers and ch == closers[-1]:
            closers.pop()
        if ch == ";" and not closers:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]
