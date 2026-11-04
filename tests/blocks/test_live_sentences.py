"""Tests for the live_sentences block: contract (ID card + SPEC) and behaviour (from SPEC.md)."""

import inspect
import json
import threading
from pathlib import Path

import pytest

import hsk_trainer.blocks.live_sentences as block
from hsk_trainer.blocks import sentence_writer
from hsk_trainer.blocks.sentence_bank import SentenceBank
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.models import Card

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "live_sentences"
    assert block.BLOCK_SPEC.kind == "script"


def test_spec_md_has_every_section():
    assert missing_spec_sections(SPEC_MD) == []


def test_inputs_and_outputs_match_spec():
    """The code's ID card (BLOCK_SPEC) and the job description (SPEC.md) agree."""
    for field, section in [("inputs", "Inputs"), ("outputs", "Outputs")]:
        listed = getattr(block.BLOCK_SPEC, field)
        text = spec_section(SPEC_MD, section)
        for item in listed:
            assert item in text, (
                f"BLOCK_SPEC.{field} has {item!r}, not in SPEC.md {section}"
            )
        if "TODO" not in text:  # once the SPEC section is filled in...
            assert listed, (
                f"SPEC.md {section} is filled in: copy it into BLOCK_SPEC.{field}"
            )


# ---- Behaviour (from SPEC.md) -----------------------------------------------------
# The block's public names are reached through `block.` (not imported at the top), so
# the contract tests above still run while the block is only a stub. A real
# SentenceBank on tmp_path files; a FAKE `write` (never Claude); a fixed rng so the
# new-or-banked draw is known. Waits are tiny so the suite stays fast.

MODEL = "fake-sonnet"
SHORT = 0.05  # a wait that a blocked job never meets
LONG = 2.0  # a wait a released job always meets (it returns as soon as it's ready)


def card(hanzi: str) -> Card:
    return Card(id=hanzi, fields={"hanzi": hanzi}, answers=["x"], level=1)


DECK = [card("爸爸"), card("吃"), card("饭"), card("我")]

A = ("我吃饭。", "wǒ chī fàn。", "I eat.")
B = ("爸爸吃饭。", "bà ba chī fàn。", "Dad eats.")
C = ("我们吃饭。", "wǒ men chī fàn。", "We eat.")


def sentence(triple):
    hanzi, pinyin, english = triple
    return sentence_writer.Sentence(hanzi=hanzi, pinyin=pinyin, english=english)


class FixedRandom:
    """An rng whose random() always returns `value`: 0.0 = always new, 0.99 = banked
    whenever the word has at least one banked sentence."""

    def __init__(self, value: float):
        self.value = value

    def random(self) -> float:
        return self.value


NEW, BANKED = FixedRandom(0.0), FixedRandom(0.99)


class FakeWrite:
    """A fake `write(card) -> WrittenSentences`.

    `results`: a list (used per call, in order; the last one repeats) or a dict by card
    id. Each result is a list of sentence triples or an exception to raise. `gate`: an
    Event the call waits on before answering (the test releases it)."""

    def __init__(self, results=None, gate=None):
        self.results = results if results is not None else [[A]]
        self.gate = gate
        self.calls: list[str] = []
        self.threads: list[threading.Thread] = []

    def __call__(self, word: Card):
        n = len(self.calls)
        self.calls.append(word.id)
        self.threads.append(threading.current_thread())
        if self.gate is not None:
            self.gate.wait(5)
        if isinstance(self.results, dict):
            result = self.results[word.id]
        else:
            result = self.results[min(n, len(self.results) - 1)]
        if isinstance(result, BaseException):
            raise result
        return sentence_writer.WrittenSentences(
            sentences=[sentence(t) for t in result], model=MODEL
        )

    def join(self, timeout: float = 2.0) -> None:
        """Wait until every background call so far has finished."""
        for t in self.threads:
            if t is not threading.current_thread():
                t.join(timeout)


@pytest.fixture
def gate():
    """An Event the fake waits on; always released at the end so no thread lingers."""
    event = threading.Event()
    yield event
    event.set()


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "sentences.jsonl", tmp_path / "sentence_seen.json"


def write_bank(path, word: str, *triples) -> None:
    """Append one bank line in sentence_writer's format."""
    row = {
        "id": word,
        "hanzi": word,
        "sentences": [{"hanzi": h, "pinyin": p, "english": e} for h, p, e in triples],
        "model": MODEL,
        "prompt_version": "2",
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_bank(paths, rng=NEW) -> SentenceBank:
    path, seen = paths
    return SentenceBank(DECK, path=path, seen_path=seen, rng=rng)


def make(bank, write, **kwargs):
    kwargs.setdefault("wait", LONG)
    return block.LiveSentences(bank, DECK, write=write, **kwargs)


def banked_hanzi(paths, word: str) -> list[str]:
    """What the bank file holds for `word` (read straight from the file)."""
    path, _ = paths
    if not path.exists():
        return []
    for text in path.read_text(encoding="utf-8").splitlines():
        if text.strip() and (row := json.loads(text))["id"] == word:
            return [s["hanzi"] for s in row["sentences"]]
    return []


def seen_hanzi(paths, word: str) -> set[str]:
    _, seen = paths
    if not seen.exists():
        return set()
    return set(json.loads(seen.read_text(encoding="utf-8")).get(word, {}))


def says_off(shown) -> bool:
    return bool(shown.note) and "off" in shown.note.lower()


# Public names and defaults (SPEC "How it's called", Outputs)


def test_defaults_match_spec():
    params = inspect.signature(block.LiveSentences).parameters
    assert params["write"].default is None
    assert params["wait"].default == 15
    assert params["max_failures"].default == 2
    assert params["enabled"].default is True
    assert params["before_waiting"].default is None


def test_shown_is_a_frozen_model():
    shown = block.Shown(sentence=sentence(A), source="new", note=None)
    assert shown.sentence == sentence(A)
    with pytest.raises(Exception):  # noqa: B017 (pydantic's frozen-instance error)
        shown.source = "banked"


# Output 1: rule says new, job ready


def test_rule_says_new_and_job_ready_shows_and_banks(paths):
    write = FakeWrite([[A]])
    live = make(make_bank(paths, NEW), write)
    live.prepare("吃")
    shown = live.sentence_for("吃")
    assert shown.source == "new"
    assert shown.sentence == sentence(A)
    assert write.calls == ["吃"]
    assert banked_hanzi(paths, "吃") == [A[0]]


def test_sentence_for_prepares_first_if_needed(paths):
    write = FakeWrite([[A]])
    shown = make(make_bank(paths, NEW), write).sentence_for("吃")
    assert shown.source == "new"
    assert write.calls == ["吃"]


def test_every_new_sentence_is_banked_and_the_first_is_shown(paths):
    live = make(make_bank(paths, NEW), FakeWrite([[B, A]]))
    shown = live.sentence_for("吃")
    assert shown.sentence == sentence(B)
    assert banked_hanzi(paths, "吃") == [B[0], A[0]]


def test_new_sentence_already_banked_is_shown_but_not_added_twice(paths):
    path, _ = paths
    write_bank(path, "吃", A)
    live = make(make_bank(paths, NEW), FakeWrite([[A]]))
    shown = live.sentence_for("吃")
    assert shown.source == "new"
    assert shown.sentence == sentence(A)
    assert banked_hanzi(paths, "吃") == [A[0]]


# Output 3: rule says banked


def test_rule_says_banked_never_calls_write(paths):
    path, _ = paths
    write_bank(path, "吃", A)
    write = FakeWrite([[B]])
    live = make(make_bank(paths, BANKED), write)
    live.prepare("吃")
    shown = live.sentence_for("吃")
    assert write.calls == []
    assert shown.source == "banked"
    assert shown.sentence == sentence(A)


# Waiting and late results


def test_waiting_calls_before_waiting_once_and_job_finishes_in_time(paths, gate):
    called = []

    def before_waiting():
        called.append(1)
        gate.set()  # the job finishes while the question waits

    write = FakeWrite([[A]], gate=gate)
    live = make(make_bank(paths, NEW), write, before_waiting=before_waiting)
    live.prepare("吃")
    shown = live.sentence_for("吃")
    assert called == [1]
    assert shown.source == "new"
    assert shown.sentence == sentence(A)


def test_not_ready_within_wait_uses_the_bank(paths, gate):
    path, _ = paths
    write_bank(path, "吃", A)
    live = make(make_bank(paths, NEW), FakeWrite([[B]], gate=gate), wait=SHORT)
    shown = live.sentence_for("吃")
    assert shown.source == "banked"
    assert shown.sentence == sentence(A)


def test_late_result_is_banked_at_the_next_sentence_for(paths, gate):
    path, _ = paths
    write_bank(path, "吃", A)
    write = FakeWrite({"吃": [B], "饭": [C]}, gate=gate)
    live = make(make_bank(paths, NEW), write, wait=SHORT)
    live.sentence_for("吃")  # too slow: the bank is used
    assert banked_hanzi(paths, "吃") == [A[0]]
    gate.set()
    write.join()
    live.sentence_for("饭")
    assert banked_hanzi(paths, "吃") == [A[0], B[0]]


def test_late_result_is_banked_at_the_next_prepare(paths, gate):
    path, _ = paths
    write_bank(path, "吃", A)
    write = FakeWrite({"吃": [B], "饭": [C]}, gate=gate)
    live = make(make_bank(paths, NEW), write, wait=SHORT)
    live.sentence_for("吃")
    gate.set()
    write.join()
    live.prepare("饭")
    assert B[0] in banked_hanzi(paths, "吃")


def test_file_writes_happen_on_the_quiz_thread(paths, gate):
    """Background threads only call `write`; add and mark_seen run on this thread."""
    bank = make_bank(paths, NEW)
    used = []
    for name in ("add", "mark_seen"):
        real = getattr(bank, name)

        def spy(*args, _real=real, **kwargs):
            used.append(threading.current_thread())
            return _real(*args, **kwargs)

        setattr(bank, name, spy)
    write = FakeWrite({"吃": [B], "饭": [C]}, gate=gate)
    live = make(bank, write, wait=SHORT)
    live.sentence_for("吃")  # late
    gate.set()
    write.join()
    live.sentence_for("饭")
    assert used
    assert all(t is threading.current_thread() for t in used)
    assert all(t is not threading.current_thread() for t in write.threads)


# Failure modes: write raises / returns nothing


@pytest.mark.parametrize("kind", ["anything", "claude-error"])
def test_write_raises_uses_the_bank(paths, kind):
    from quizkit.claude import ClaudeError

    error = ClaudeError("usage limit reached") if kind == "claude-error" else None
    error = error or RuntimeError("boom")
    path, _ = paths
    write_bank(path, "吃", A)
    shown = make(make_bank(paths, NEW), FakeWrite([error])).sentence_for("吃")
    assert shown.source == "banked"
    assert shown.sentence == sentence(A)


def test_write_returns_no_sentences_uses_the_bank(paths):
    path, _ = paths
    write_bank(path, "吃", A)
    shown = make(make_bank(paths, NEW), FakeWrite([[]])).sentence_for("吃")
    assert shown.source == "banked"
    assert shown.sentence == sentence(A)


def test_failure_with_an_empty_bank_shows_none(paths):
    shown = make(make_bank(paths, NEW), FakeWrite([[]])).sentence_for("吃")
    assert shown.source == "none"
    assert shown.sentence is None


# Failure modes: switching off after max_failures in a row


def test_two_failures_in_a_row_switch_live_off_with_a_note(paths):
    write = FakeWrite([RuntimeError("boom")])
    live = make(make_bank(paths, NEW), write)
    first = live.sentence_for("吃")
    second = live.sentence_for("饭")
    assert not says_off(first)
    assert says_off(second)
    live.prepare("我")
    third = live.sentence_for("我")
    assert write.calls == ["吃", "饭"]  # no more jobs
    assert third.source == "none"


def test_empty_results_count_as_failures(paths):
    write = FakeWrite([[]])
    live = make(make_bank(paths, NEW), write)
    live.sentence_for("吃")
    assert says_off(live.sentence_for("饭"))
    live.sentence_for("我")
    assert write.calls == ["吃", "饭"]


def test_timeouts_count_as_failures(paths, gate):
    write = FakeWrite([[A]], gate=gate)
    live = make(make_bank(paths, NEW), write, wait=SHORT)
    live.sentence_for("吃")
    assert says_off(live.sentence_for("饭"))
    live.sentence_for("我")
    assert write.calls == ["吃", "饭"]


def test_max_failures_is_a_setting(paths):
    write = FakeWrite([RuntimeError("boom")])
    live = make(make_bank(paths, NEW), write, max_failures=1)
    assert says_off(live.sentence_for("吃"))
    live.sentence_for("饭")
    assert write.calls == ["吃"]


def test_a_success_resets_the_failure_count(paths):
    boom = RuntimeError("boom")
    write = FakeWrite([boom, [A], boom, [B]])
    live = make(make_bank(paths, NEW), write)
    live.sentence_for("吃")  # fail
    live.sentence_for("饭")  # success: count back to 0
    third = live.sentence_for("我")  # fail (1 in a row, not 2)
    shown = live.sentence_for("爸爸")
    assert not says_off(third)
    assert write.calls == ["吃", "饭", "我", "爸爸"]
    assert shown.source == "new"
    assert shown.sentence == sentence(B)


# Failure modes: enabled=False


def test_enabled_false_never_calls_write(paths):
    path, _ = paths
    write_bank(path, "吃", A)
    write = FakeWrite([[B]])
    live = make(make_bank(paths, NEW), write, enabled=False)
    live.prepare("吃")
    banked = live.sentence_for("吃")
    empty = live.sentence_for("饭")
    assert write.calls == []
    assert (banked.source, banked.sentence) == ("banked", sentence(A))
    assert (empty.source, empty.sentence) == ("none", None)


# Output 4: mark_seen


def test_banked_sentence_is_marked_seen(paths):
    path, _ = paths
    write_bank(path, "吃", A)
    make(make_bank(paths, BANKED), FakeWrite()).sentence_for("吃")
    assert seen_hanzi(paths, "吃") == {A[0]}


def test_new_sentence_is_marked_seen(paths):
    make(make_bank(paths, NEW), FakeWrite([[B]])).sentence_for("吃")
    assert seen_hanzi(paths, "吃") == {B[0]}


def test_mark_seen_os_error_still_shows_with_a_note_once(paths):
    path, _ = paths
    write_bank(path, "吃", A)
    write_bank(path, "饭", C)
    bank = make_bank(paths, BANKED)

    def locked(*args, **kwargs):
        raise PermissionError("locked")

    bank.mark_seen = locked
    live = make(bank, FakeWrite())
    first = live.sentence_for("吃")
    second = live.sentence_for("饭")
    assert first.sentence == sentence(A)
    assert first.note and "seen" in first.note.lower()
    assert second.sentence == sentence(C)
    assert second.note is None


# Failure modes: unknown ids, prepare twice, daemon threads


@pytest.mark.parametrize("method", ["prepare", "sentence_for"])
def test_unknown_card_id_raises_value_error(paths, method):
    live = make(make_bank(paths, NEW), FakeWrite())
    with pytest.raises(ValueError):
        getattr(live, method)("nope")


def test_prepare_twice_starts_one_job(paths):
    write = FakeWrite([[A]])
    live = make(make_bank(paths, NEW), write)
    live.prepare("吃")
    live.prepare("吃")
    live.sentence_for("吃")
    assert write.calls == ["吃"]


def test_background_threads_are_daemons(paths, gate):
    write = FakeWrite([[A]], gate=gate)
    live = make(make_bank(paths, NEW), write)
    live.prepare("吃")
    gate.set()
    live.sentence_for("吃")
    (thread,) = write.threads
    assert thread is not threading.current_thread()
    assert thread.daemon


# -- block-review round 1 --------------------------------------------------------------


def locked(*args, **kwargs):
    raise PermissionError("locked")


@pytest.mark.parametrize("late", [RuntimeError("timed out"), []])
def test_late_job_that_fails_is_dropped_quietly(paths, gate, late):
    """Claude hangs past `wait`, then its error (or nothing) arrives: no crash."""
    write = FakeWrite({"吃": late, "饭": [C]}, gate=gate)
    live = make(make_bank(paths, NEW), write, wait=SHORT, max_failures=3)
    live.sentence_for("吃")  # timed out: failure 1
    gate.set()
    write.join()
    shown = live.sentence_for("饭")
    assert (shown.source, shown.sentence) == ("new", sentence(C))
    assert banked_hanzi(paths, "吃") == []


def test_bank_add_os_error_still_shows_with_a_note_once(paths):
    bank = make_bank(paths, NEW)
    bank.add = locked
    live = make(bank, FakeWrite({"吃": [A], "饭": [C]}))
    first, second = live.sentence_for("吃"), live.sentence_for("饭")
    assert (first.source, first.sentence) == ("new", sentence(A))
    assert first.note and "save" in first.note.lower()
    assert (second.sentence, second.note) == (sentence(C), None)


def test_a_note_from_late_banking_comes_with_the_next_shown(paths, gate):
    bank = make_bank(paths, NEW)
    write = FakeWrite({"吃": [B], "饭": [C]}, gate=gate)
    live = make(bank, write, wait=SHORT)
    live.sentence_for("吃")  # late
    gate.set()
    write.join()
    bank.add = locked
    shown = live.sentence_for("饭")
    assert shown.note and "save" in shown.note.lower()


def test_after_switching_off_a_finished_job_is_still_used(paths):
    boom = RuntimeError("boom")
    write = FakeWrite({"吃": boom, "饭": boom, "我": [A]})
    live = make(make_bank(paths, NEW), write)
    live.prepare("我")
    write.join()  # 我 is finished before live switches off
    live.sentence_for("吃")
    assert says_off(live.sentence_for("饭"))
    shown = live.sentence_for("我")
    assert (shown.source, shown.sentence) == ("new", sentence(A))


def test_after_switching_off_an_unfinished_job_is_not_waited_for(paths, gate):
    called = []

    def write(word):
        if word.id == "我":
            gate.wait(5)  # still being written when its question comes
            return sentence_writer.WrittenSentences(
                sentences=[sentence(A)], model=MODEL
            )
        raise RuntimeError("boom")

    live = make(
        make_bank(paths, NEW),
        write,
        wait=LONG,
        max_failures=1,
        before_waiting=lambda: called.append(1),
    )
    live.prepare("我")
    assert says_off(live.sentence_for("吃"))
    called.clear()
    shown = live.sentence_for("我")
    assert called == []  # never waited
    assert (shown.source, shown.note) == ("none", None)  # no second "off" note


def test_a_finished_job_never_calls_before_waiting(paths):
    called = []
    write = FakeWrite([[A]])
    live = make(make_bank(paths, NEW), write, before_waiting=lambda: called.append(1))
    live.prepare("吃")
    write.join()
    assert live.sentence_for("吃").source == "new"
    assert called == []


# -- /code-review round 1 --------------------------------------------------------------


def test_finish_banks_a_sentence_still_being_written(paths, gate):
    write = FakeWrite({"吃": [B]}, gate=gate)
    live = make(make_bank(paths, NEW), write, wait=SHORT)
    live.sentence_for("吃")  # too slow
    threading.Timer(0.05, gate.set).start()  # finishes during finish()
    assert live.finish(seconds=2) == []
    assert banked_hanzi(paths, "吃") == [B[0]]


def test_finish_banks_a_prepared_job_never_asked(paths):
    write = FakeWrite([[A]])
    live = make(make_bank(paths, NEW), write)
    live.prepare("吃")  # e.g. the quiz was quit before this question
    live.finish(seconds=2)
    assert banked_hanzi(paths, "吃") == [A[0]]


def test_finish_does_not_wait_past_its_limit(paths, gate):
    import time

    live = make(make_bank(paths, NEW), FakeWrite([[A]], gate=gate))
    live.prepare("吃")
    start = time.monotonic()
    live.finish(seconds=SHORT)
    assert time.monotonic() - start < 1
    assert banked_hanzi(paths, "吃") == []


def test_default_writer_problem_counts_as_a_failure(paths, monkeypatch):
    """A bad word list (built on the first call) is a failure, not a crash."""

    def broken(cards):
        raise ValueError("two cards share a hanzi")

    monkeypatch.setattr(block, "Vocab", broken)
    path, _ = paths
    write_bank(path, "吃", A)
    live = block.LiveSentences(make_bank(paths, NEW), DECK, wait=LONG)
    shown = live.sentence_for("吃")
    assert (shown.source, shown.sentence) == ("banked", sentence(A))


def test_save_note_names_the_word(paths):
    bank = make_bank(paths, NEW)
    bank.add = locked
    shown = make(bank, FakeWrite([[A]])).sentence_for("吃")
    assert "吃" in shown.note
