"""sentence_bank: Keep the bank of checked example sentences: pick, for a word, a new or
a banked sentence by the ADR 0011 rule, remember when each was seen, and add new ones.

See SPEC.md in this folder (ADR 0003, ADR 0011). A script: plain bookkeeping. The bank
is sentence_writer's file, data/generated/sentences.jsonl; it trusts it (every sentence
is checked before it's saved).
"""

import json
import random
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hsk_trainer.blocks.sentence_writer import (
    MAX_SAVED,
    PROMPT_VERSION,
    ROOT,
    SENTENCES_FILE,
    Sentence,
    SentenceFileError,
    SentenceLine,
    read_lines,
    write_lines,
)
from quizkit.blocks.base import BlockSpec
from quizkit.files import write_atomically
from quizkit.models import Card

BLOCK_SPEC = BlockSpec(
    name="sentence_bank",
    kind="script",
    goal="Keep the bank of checked example sentences: pick, for a word, a new or a banked sentence by the ADR 0011 rule, remember when each was seen, and add new ones.",
    inputs=["cards", "path", "seen_path", "removed_path", "settings", "rng", "now"],
    outputs=[
        "chance_of_new",
        "wants_new",
        "banked",
        "data/sentence_seen.json",
        "data/generated/sentences.jsonl",
        "data/generated/sentences_removed.json",
    ],
)

SEEN_FILE = ROOT / "data" / "sentence_seen.json"  # gitignored: your history, not source
# Sentences an audit removed (ADR 0015): committed, never banked or shown again.
REMOVED_FILE = ROOT / "data" / "generated" / "sentences_removed.json"


class BankSettings(BaseModel):
    """The ADR 0011 rule's knobs."""

    model_config = ConfigDict(frozen=True)

    floor: float = Field(default=0.2, ge=0, le=1)  # lowest chance of a new sentence
    # Most sentences kept per word. Never above MAX_SAVED: sentence_writer would
    # treat a longer line as broken and redo it, losing the banked sentences.
    cap: int = Field(default=MAX_SAVED, ge=1, le=MAX_SAVED)


def _later(a: str, b: str) -> bool:
    return datetime.fromisoformat(a) > datetime.fromisoformat(b)


def _read_seen(path: Path, quiet: bool = False) -> dict[str, dict[str, str]]:
    """The seen file, or {} if it's missing or unreadable (a warning for unreadable,
    unless `quiet`)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("not an object")
        for word, times in data.items():
            if not isinstance(times, dict):
                raise TypeError(f"{word!r} is not an object")
            for when in times.values():
                if datetime.fromisoformat(when).tzinfo is None:  # ISO, with a zone
                    raise ValueError(f"{when!r} has no timezone")
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as err:
        if not quiet:
            print(
                f"Warning: can't read {path.name} ({err}); starting with nothing seen"
            )
        return {}
    return data


class RemovedListError(SentenceFileError):
    """The removed list can't be read (a SentenceFileError, so old callers still
    catch it; new ones can name the right file)."""


def _read_removed(path: Path) -> dict[str, list[str]]:
    """The removed list, or {} if it's missing. Committed data, so a broken one is
    loud (SentenceFileError naming the file), like the bank itself."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("not an object of word -> list of sentences")
        for word, sentences in data.items():
            if not isinstance(sentences, list) or not all(
                isinstance(s, str) for s in sentences
            ):
                raise TypeError(f"{word!r} is not a list of sentences (text)")
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as err:
        raise RemovedListError(f"{path.name}: {err}") from err
    return data


class SentenceBank:
    """The bank for one quiz: read once, saved after every change."""

    def __init__(
        self,
        cards: list[Card],
        path: Path = SENTENCES_FILE,
        seen_path: Path = SEEN_FILE,
        removed_path: Path = REMOVED_FILE,
        settings: BankSettings | None = None,
        rng: random.Random | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.cards = cards
        self.known = {c.id for c in cards}
        self.path = path
        self.seen_path = seen_path
        self.settings = settings or BankSettings()
        self.rng = rng or random.Random()
        self.now = now or (lambda: datetime.now(UTC))
        self.lines: dict[str, SentenceLine] = {}  # first line per known id
        # Lines for other ids, and later copies of an id: kept as they are.
        self.others: list[SentenceLine] = []
        for line in read_lines(path) if path.exists() else []:
            if line.id in self.known and line.id not in self.lines:
                self.lines[line.id] = line
            else:
                self.others.append(line)
        self.seen = _read_seen(seen_path)
        self.removed_path = removed_path
        self._set_removed(_read_removed(removed_path))

    def _check(self, card_id: str) -> None:
        if card_id not in self.known:
            raise ValueError(f"{card_id!r} is not one of the cards")

    def _set_removed(self, removed: dict[str, list[str]]) -> None:
        """Keep the list (for writing, in order) and a set per word (for lookups)."""
        self.removed = removed
        self._listed = {word: set(items) for word, items in removed.items()}

    def _sentences(self, card_id: str) -> list[Sentence]:
        """The word's usable sentences: in its line, and not on the removed list."""
        self._check(card_id)
        line = self.lines.get(card_id)
        listed = self._listed.get(card_id, set())
        return [s for s in line.sentences if s.hanzi not in listed] if line else []

    def is_removed(self, card_id: str, hanzi: str) -> bool:
        """Is this sentence on the removed list (ADR 0015)?"""
        self._check(card_id)
        return hanzi in self._listed.get(card_id, set())

    def remove(self, card_id: str, hanzi: str) -> bool:
        """An audit's removal (ADR 0015): list it (saved first), then take it out of
        the word's line (a line left empty is dropped). True if the bank was using it."""
        self._check(card_id)
        was_used = any(s.hanzi == hanzi for s in self._sentences(card_id))
        # Merge with the list on disk first: another bank (an audit, a quiz) may have
        # listed more since this one was made, and must not be overwritten.
        on_disk = _read_removed(self.removed_path)
        merged = {
            word: list(dict.fromkeys([*on_disk.get(word, []), *items]))
            for word, items in {**self.removed, **on_disk}.items()
        }
        for word, items in self.removed.items():  # words only this bank listed
            merged[word] = list(dict.fromkeys([*merged.get(word, []), *items]))
        if hanzi not in merged.get(card_id, []):
            merged[card_id] = [*merged.get(card_id, []), hanzi]
        if merged != on_disk:
            self.removed_path.parent.mkdir(parents=True, exist_ok=True)
            data = json.dumps(merged, ensure_ascii=False, indent=1) + "\n"
            write_atomically(self.removed_path, data.encode("utf-8"))
        self._set_removed(merged)
        line = self.lines.get(card_id)
        kept = [s for s in line.sentences if s.hanzi != hanzi] if line else []
        if line is not None and len(kept) != len(line.sentences):
            if kept:
                self.lines[card_id] = line.model_copy(update={"sentences": kept})
            else:
                del self.lines[card_id]
            self._save()
        return was_used

    def count(self, card_id: str) -> int:
        """How many sentences the word has in the bank."""
        return len(self._sentences(card_id))

    def chance_of_new(self, card_id: str) -> float:
        """ADR 0011: max(floor, 1 / (1 + banked)). 0 banked → 1.0, 1 → 0.5, 3 → 0.25."""
        return max(self.settings.floor, 1 / (1 + self.count(card_id)))

    def wants_new(self, card_id: str) -> bool:
        """One draw: should this question get a new sentence?"""
        return self.rng.random() < self.chance_of_new(card_id)

    def banked(self, card_id: str) -> Sentence | None:
        """The word's least recently seen sentence (never seen first, in file order)."""
        sentences = self._sentences(card_id)
        if not sentences:
            return None
        times = self.seen.get(card_id, {})
        never = [s for s in sentences if s.hanzi not in times]
        if never:
            return never[0]
        return min(sentences, key=lambda s: datetime.fromisoformat(times[s.hanzi]))

    def mark_seen(self, card_id: str, sentence: Sentence) -> None:
        """Remember that `sentence` was shown now (saved at once)."""
        self._check(card_id)
        # Merge with the file first: another quiz may have saved since this one began.
        for word, times in _read_seen(self.seen_path, quiet=True).items():
            mine = self.seen.setdefault(word, {})
            for hanzi, when in times.items():
                if hanzi not in mine or _later(when, mine[hanzi]):
                    mine[hanzi] = when
        self.seen.setdefault(card_id, {})[sentence.hanzi] = self.now().isoformat()
        self.seen_path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.seen, ensure_ascii=False, indent=1) + "\n"
        write_atomically(self.seen_path, data.encode("utf-8"))

    def add(self, card_id: str, sentence: Sentence, model: str) -> bool:
        """Save a new, already checked sentence. False if it's banked already, on the
        removed list, or the word is full (`cap`). Listed sentences still in the line
        are dropped as it's rewritten, so a line never grows past `cap`."""
        sentences = self._sentences(card_id)  # usable only: listed ones are left out
        if (
            len(sentences) >= self.settings.cap
            or any(s.hanzi == sentence.hanzi for s in sentences)
            or self.is_removed(card_id, sentence.hanzi)
        ):
            return False
        word = next(c for c in self.cards if c.id == card_id)
        old = self.lines.get(card_id)
        self.lines[card_id] = SentenceLine(
            id=card_id,
            hanzi=old.hanzi if old else word.fields.get("hanzi", card_id),
            sentences=[*sentences, sentence],
            model=model,
            prompt_version=old.prompt_version if old else PROMPT_VERSION,
        )
        self._save()
        return True

    def _save(self) -> None:
        """Cards order first, then every other line as it was: the file never
        shrinks, except through `remove`."""
        rows = [self.lines[c.id] for c in self.cards if c.id in self.lines]
        write_lines(self.path, rows + self.others)
