"""live_sentences: During the quiz, get each sentence-mode question its sentence: ask Claude ahead in the background when the bank's rule says new, bank what passes, and fall back to the bank when Claude is slow or failing.

See SPEC.md in this folder (ADR 0003, ADR 0011).
"""

import threading
import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from hsk_trainer.blocks.sentence_bank import SentenceBank
from hsk_trainer.blocks.sentence_validator import Vocab
from hsk_trainer.blocks.sentence_writer import Sentence, WrittenSentences, write_one
from quizkit.blocks.base import BlockSpec
from quizkit.models import Card

BLOCK_SPEC = BlockSpec(
    name="live_sentences",
    kind="script",
    goal="During the quiz, get each sentence-mode question its sentence: ask Claude ahead in the background when the bank's rule says new, bank what passes, and fall back to the bank when Claude is slow or failing.",
    inputs=[
        "bank",
        "cards",
        "write",
        "wait",
        "max_failures",
        "enabled",
        "before_waiting",
    ],
    outputs=["Shown"],
)


class Shown(BaseModel):
    """The sentence to show for one question, where it came from, and a note."""

    model_config = ConfigDict(frozen=True)

    sentence: Sentence | None
    source: Literal["new", "banked", "none"]
    note: str | None = None


def _wait(event: threading.Event, seconds: float) -> bool:
    """event.wait in short slices, so Ctrl-C stops the quiz at once on Windows too."""
    deadline = time.monotonic() + seconds
    while not event.is_set():
        left = deadline - time.monotonic()
        if left <= 0:
            return False
        event.wait(min(left, 0.1))
    return True


class _Job:
    """One background `write` call. The thread only sets `result` or `error`."""

    def __init__(self, card: Card, write: Callable[[Card], WrittenSentences]):
        self.card = card
        self.done = threading.Event()
        self.result: WrittenSentences | None = None
        self.error: Exception | None = None
        self.thread = threading.Thread(
            target=self._run, args=(write,), daemon=True, name=f"live:{card.id}"
        )
        self.thread.start()

    def _run(self, write: Callable[[Card], WrittenSentences]) -> None:
        try:
            self.result = write(self.card)
        except Exception as err:  # noqa: BLE001 (any failure = one failure; the quiz goes on)
            self.error = err
        finally:
            self.done.set()

    @property
    def sentences(self) -> list[Sentence]:
        return self.result.sentences if self.result is not None else []


def _default_writer(cards: list[Card]) -> Callable[[Card], WrittenSentences]:
    """write_one with the word list built once, on the first call (in the background):
    a bad cards file then counts as one failure instead of stopping the quiz."""
    vocab: list[Vocab] = []
    lock = threading.Lock()

    def write(card: Card) -> WrittenSentences:
        with lock:
            if not vocab:
                vocab.append(Vocab(cards))
        return write_one(card, cards, vocab[0])

    return write


class LiveSentences:
    """New sentences while you play, the bank as the fallback (ADR 0011)."""

    def __init__(
        self,
        bank: SentenceBank,
        cards: list[Card],
        write: Callable[[Card], WrittenSentences] | None = None,
        wait: float = 15.0,
        max_failures: int = 2,
        enabled: bool = True,
        before_waiting: Callable[[], None] | None = None,
    ):
        self.bank = bank
        self.cards = {c.id: c for c in cards}
        self.write = write or _default_writer(cards)
        self.wait = wait
        self.max_failures = max_failures
        self.live = enabled  # False from the start, or after max_failures in a row
        self.before_waiting = before_waiting
        self.failures = 0  # in a row
        self.drawn: dict[str, _Job | None] = {}  # prepared: a job if the rule said new
        self.late: list[_Job] = []  # moved on before they finished
        self.pending: list[str] = []  # notes from late jobs, shown with the next one
        self.warned_seen = False
        self.warned_add = False

    # -- public -----------------------------------------------------------------

    def prepare(self, card_id: str) -> None:
        """Draw new-or-banked for this question now; if new, start writing."""
        self._check(card_id)
        self._bank_late()
        if card_id in self.drawn:
            return
        new = self.live and self.bank.wants_new(card_id)
        self.drawn[card_id] = _Job(self.cards[card_id], self.write) if new else None

    def sentence_for(self, card_id: str) -> Shown:
        """The sentence to show now (prepares first if needed)."""
        self.prepare(card_id)
        job = self.drawn.pop(card_id)
        notes, self.pending = self.pending, []
        sentence: Sentence | None = None
        if job is not None:
            sentence = self._use(job, notes)
        source: Literal["new", "banked", "none"] = "new"
        if sentence is None:
            sentence = self.bank.banked(card_id)
            source = "banked" if sentence is not None else "none"
        if sentence is not None:
            self._mark_seen(card_id, sentence, notes)
        return Shown(sentence=sentence, source=source, note="; ".join(notes) or None)

    def finish(self, seconds: float = 5.0) -> list[str]:
        """End of the quiz: wait up to `seconds` for sentences still being written and
        bank them, so a paid call isn't lost. Returns any notes. Ctrl-C skips the wait."""
        jobs = self.late + [j for j in self.drawn.values() if j is not None]
        self.late, self.drawn = jobs, {}
        deadline = time.monotonic() + seconds
        try:
            for job in jobs:
                _wait(job.done, max(0.0, deadline - time.monotonic()))
        except KeyboardInterrupt:
            pass
        self._bank_late()
        notes, self.pending = self.pending, []
        return notes

    # -- inside -----------------------------------------------------------------

    def _check(self, card_id: str) -> None:
        if card_id not in self.cards:
            raise ValueError(f"{card_id!r} is not one of the cards")

    def _use(self, job: _Job, notes: list[str]) -> Sentence | None:
        """The job's first sentence (all of them banked), or None after a failure."""
        if not job.done.is_set():
            if not self.live:  # switched off since it started: never wait
                self.late.append(job)
                return None
            if self.before_waiting is not None:
                self.before_waiting()
            if not _wait(job.done, self.wait):
                self.late.append(job)  # banked later if it finishes
                self._failed("Claude took too long", notes)
                return None
        if job.sentences:
            self._bank(job, notes)
            self.failures = 0
            return job.sentences[0]
        if self.live:
            reason = str(job.error) if job.error else "no sentence passed the checks"
            self._failed(reason, notes)
        return None

    def _failed(self, reason: str, notes: list[str]) -> None:
        self.failures += 1
        if self.live and self.failures >= self.max_failures:
            self.live = False
            notes.append(f"live sentences switched off for this quiz: {reason}")

    def _bank_late(self) -> None:
        """Bank what finished after its question moved on (no effect on failures)."""
        still: list[_Job] = []
        for job in self.late:
            if job.done.is_set():
                self._bank(job, self.pending)
            else:
                still.append(job)
        self.late = still

    def _bank(self, job: _Job, notes: list[str]) -> None:
        if job.result is None:  # it raised: nothing to bank (a late failure)
            return
        for sentence in job.sentences:  # the bank refuses repeats and a full word
            try:
                self.bank.add(job.card.id, sentence, job.result.model)
            except OSError as err:
                if not self.warned_add:
                    notes.append(
                        f"couldn't save a new sentence for {job.card.id}: {err}"
                    )
                    self.warned_add = True
                return

    def _mark_seen(self, card_id: str, sentence: Sentence, notes: list[str]) -> None:
        try:
            self.bank.mark_seen(card_id, sentence)
        except OSError as err:  # e.g. OneDrive or antivirus has it locked: carry on
            if not self.warned_seen:
                notes.append(f"couldn't save which sentences you've seen: {err}")
                self.warned_seen = True
