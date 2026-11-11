"""Tests for the sentence_bank block: contract (ID card + SPEC) and behaviour (from SPEC.md)."""

import inspect
import json
import os
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

import hsk_trainer.blocks.sentence_bank as block
from hsk_trainer.blocks import sentence_writer
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.models import Card

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "sentence_bank"
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
# the contract tests above still run while the block is only a stub. The bank trusts
# its file (SPEC "Not re-checked here"), so the toy sentences need not pass any check.

MODEL = "fake-sonnet"


def card(hanzi: str, pinyin: str) -> Card:
    return Card(
        id=hanzi, fields={"hanzi": hanzi, "pinyin": pinyin}, answers=["x"], level=1
    )


# Cards order (like cards.jsonl).
DECK = [card("爸爸", "bà ba"), card("吃", "chī"), card("饭", "fàn"), card("我", "wǒ")]
IDS = [c.id for c in DECK]

A = ("我吃饭。", "wǒ chī fàn。", "I eat.")
B = ("爸爸吃饭。", "bà ba chī fàn。", "Dad eats.")
C = ("我们吃饭。", "wǒ men chī fàn。", "We eat.")
D = ("吃吧。", "chī ba。", "Eat.")
E = ("他吃。", "tā chī。", "He eats.")


def sentence(triple):
    hanzi, pinyin, english = triple
    return sentence_writer.Sentence(hanzi=hanzi, pinyin=pinyin, english=english)


def line(word: str, *triples, version: str = "2") -> str:
    """One bank line in sentence_writer's format."""
    return json.dumps(
        {
            "id": word,
            "hanzi": word,
            "sentences": [
                {"hanzi": h, "pinyin": p, "english": e} for h, p, e in triples
            ],
            "model": MODEL,
            "prompt_version": version,
        },
        ensure_ascii=False,
    )


class Clock:
    """A fake `now`: each call is one minute later than the last."""

    def __init__(self):
        self.t = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
        self.given: list[datetime] = []

    def __call__(self) -> datetime:
        self.t += timedelta(minutes=1)
        self.given.append(self.t)
        return self.t


class FixedRandom:
    """An rng whose random() always returns `value`."""

    def __init__(self, value: float):
        self.value = value

    def random(self) -> float:
        return self.value


@pytest.fixture
def files(tmp_path):
    return tmp_path / "sentences.jsonl", tmp_path / "sentence_seen.json"


def write_bank(path, *rows):
    path.write_text("".join(r + "\n" for r in rows), encoding="utf-8")


def make(files, cards=DECK, settings=None, rng=None, now=None):
    """A bank on tmp_path files (its removed list too, never the committed one)."""
    path, seen = files
    return block.SentenceBank(
        cards,
        path=path,
        seen_path=seen,
        removed_path=path.parent / "sentences_removed.json",
        settings=settings or block.BankSettings(),
        rng=rng or random.Random(0),
        now=now or Clock(),
    )


def rows(path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    return [json.loads(t) for t in text.splitlines() if t.strip()]


def by_id(path) -> dict[str, dict]:
    return {r["id"]: r for r in rows(path)}


def hanzi_of(path, word) -> list[str]:
    return [s["hanzi"] for s in by_id(path)[word]["sentences"]]


def broken_replace(src, dst):
    raise OSError("disk full")


# Public names and defaults (SPEC Inputs, "How it's called")


def test_default_files_match_spec():
    params = inspect.signature(block.SentenceBank).parameters
    assert params["path"].default == sentence_writer.SENTENCES_FILE
    assert params["seen_path"].default == block.SEEN_FILE
    assert block.SEEN_FILE.name == "sentence_seen.json"
    assert block.SEEN_FILE.parent.name == "data"
    assert params["rng"].default is None
    assert params["now"].default is None


def test_bank_settings_defaults():
    settings = block.BankSettings()
    assert settings.floor == pytest.approx(0.2)
    assert settings.cap == 10


def test_bank_works_with_default_rng_and_clock(files):
    path, seen = files
    write_bank(path, line("吃", A))
    bank = block.SentenceBank(
        DECK, path=path, seen_path=seen, removed_path=path.parent / "removed.json"
    )
    assert isinstance(bank.wants_new("吃"), bool)
    bank.mark_seen("吃", sentence(A))
    assert "吃" in json.loads(seen.read_text(encoding="utf-8"))


# Output 1: chance_of_new / wants_new (ADR 0011)


@pytest.mark.parametrize(
    ("banked", "chance"),
    [(0, 1.0), (1, 0.5), (2, 1 / 3), (3, 0.25), (4, 0.2), (5, 0.2)],
)
def test_chance_of_new_follows_the_adr_rule(files, banked, chance):
    path, _ = files
    write_bank(path, line("吃", *[A, B, C, D, E][:banked]))
    bank = make(files)
    assert bank.count("吃") == banked
    assert bank.chance_of_new("吃") == pytest.approx(chance)


def test_custom_floor_is_used(files):
    path, _ = files
    floor = block.BankSettings(floor=0.4)
    write_bank(path, line("吃", A, B, C))
    assert make(files, settings=floor).chance_of_new("吃") == pytest.approx(0.4)
    write_bank(path, line("吃", A))  # 1/2 is above the floor
    assert make(files, settings=floor).chance_of_new("吃") == pytest.approx(0.5)


def test_wants_new_is_always_true_with_nothing_banked(files):
    bank = make(files, rng=random.Random(7))
    assert all(bank.wants_new("吃") for _ in range(200))


def test_wants_new_compares_one_draw_with_the_chance(files):
    path, _ = files
    write_bank(path, line("吃", A))  # chance 0.5
    assert make(files, rng=FixedRandom(0.49)).wants_new("吃") is True
    assert make(files, rng=FixedRandom(0.51)).wants_new("吃") is False


def test_wants_new_follows_a_seeded_rng(files):
    path, _ = files
    write_bank(path, line("吃", A, B, C))  # chance 0.25
    bank = make(files, rng=random.Random(42))
    mirror = random.Random(42)
    got = [bank.wants_new("吃") for _ in range(50)]
    assert got == [mirror.random() < 0.25 for _ in range(50)]
    assert any(got) and not all(got)


# Output 2: banked


def test_banked_is_none_for_a_word_with_no_sentences(files):
    path, _ = files
    write_bank(path, line("吃", A))
    assert make(files).banked("饭") is None


def test_banked_returns_a_sentence_from_the_file(files):
    path, _ = files
    write_bank(path, line("吃", A))
    got = make(files).banked("吃")
    assert isinstance(got, sentence_writer.Sentence)
    assert got == sentence(A)


def test_banked_picks_never_seen_first_in_file_order(files):
    path, _ = files
    write_bank(path, line("吃", A, B, C))
    bank = make(files)
    assert bank.banked("吃") == sentence(A)
    bank.mark_seen("吃", sentence(A))
    assert bank.banked("吃") == sentence(B)
    bank.mark_seen("吃", sentence(B))
    assert bank.banked("吃") == sentence(C)


def test_banked_picks_the_least_recently_seen_once_all_are_seen(files):
    path, _ = files
    write_bank(path, line("吃", A, B, C))
    bank = make(files)
    for one in (B, C, A):  # seen in this order, a minute apart
        bank.mark_seen("吃", sentence(one))
    assert bank.banked("吃") == sentence(B)
    bank.mark_seen("吃", sentence(B))
    assert bank.banked("吃") == sentence(C)


def test_seen_times_are_per_word(files):
    """The same hanzi under two words: seeing it for one doesn't count for the other."""
    path, _ = files
    write_bank(path, line("吃", A, B), line("饭", A, C))
    bank = make(files)
    bank.mark_seen("吃", sentence(A))
    assert bank.banked("饭") == sentence(A)


# Output 3: the seen file


def test_mark_seen_writes_spec_shape_with_the_clock_time(files):
    path, seen = files
    write_bank(path, line("吃", A, B))
    clock = Clock()
    make(files, now=clock).mark_seen("吃", sentence(B))
    data = json.loads(seen.read_text(encoding="utf-8"))
    assert set(data) == {"吃"}
    assert set(data["吃"]) == {B[0]}
    assert datetime.fromisoformat(data["吃"][B[0]]) == clock.given[-1]


def test_mark_seen_is_read_back_by_a_new_bank(files):
    path, _ = files
    write_bank(path, line("吃", A, B))
    clock = Clock()
    make(files, now=clock).mark_seen("吃", sentence(A))
    assert make(files, now=clock).banked("吃") == sentence(B)


def test_mark_seen_keeps_earlier_entries(files):
    path, seen = files
    write_bank(path, line("吃", A), line("饭", C))
    bank = make(files)
    bank.mark_seen("吃", sentence(A))
    bank.mark_seen("饭", sentence(C))
    assert set(json.loads(seen.read_text(encoding="utf-8"))) == {"吃", "饭"}


def test_mark_seen_writes_atomically(files, monkeypatch):
    """A failed write leaves the old seen file whole (temp file + swap)."""
    path, seen = files
    write_bank(path, line("吃", A, B))
    bank = make(files)
    bank.mark_seen("吃", sentence(A))
    before = seen.read_bytes()
    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        bank.mark_seen("吃", sentence(B))
    assert seen.read_bytes() == before


# Output 4: add


def test_add_appends_to_the_words_line(files):
    path, _ = files
    write_bank(path, line("吃", A))
    bank = make(files)
    assert bank.add("吃", sentence(B), MODEL) is True
    assert hanzi_of(path, "吃") == [A[0], B[0]]
    assert bank.count("吃") == 2  # this bank knows at once
    assert make(files).count("吃") == 2  # and a new bank reads it back
    saved = by_id(path)["吃"]["sentences"][1]
    assert saved == {"hanzi": B[0], "pinyin": B[1], "english": B[2]}


def test_add_makes_a_new_line_with_model_and_prompt_version(files):
    path, _ = files
    write_bank(path, line("吃", A))
    assert make(files).add("饭", sentence(C), MODEL) is True
    row = by_id(path)["饭"]
    assert row["hanzi"] == "饭"
    assert row["model"] == MODEL
    assert str(row["prompt_version"]) == sentence_writer.PROMPT_VERSION
    assert hanzi_of(path, "饭") == [C[0]]
    sentence_writer.SentenceLine.model_validate(row)  # sentence_writer can read it


def test_add_to_a_missing_bank_makes_the_file(files):
    path, _ = files
    assert make(files).add("吃", sentence(A), MODEL) is True
    assert [r["id"] for r in rows(path)] == ["吃"]


def test_add_refuses_a_duplicate_hanzi(files):
    path, _ = files
    write_bank(path, line("吃", A))
    before = path.read_bytes()
    same_hanzi = sentence((A[0], A[1], "I am eating."))
    assert make(files).add("吃", same_hanzi, MODEL) is False
    assert path.read_bytes() == before


def test_add_refuses_a_full_word_and_writes_nothing(files):
    path, _ = files
    write_bank(path, line("吃", A, B))
    before = path.read_bytes()
    bank = make(files, settings=block.BankSettings(cap=2))
    assert bank.add("吃", sentence(C), MODEL) is False
    assert path.read_bytes() == before
    assert bank.count("吃") == 2


def test_add_fills_up_to_the_default_cap_of_ten(files):
    bank = make(files)
    added = [
        bank.add("吃", sentence((f"吃{i}。", f"chī {i}。", f"Eat {i}.")), MODEL)
        for i in range(11)
    ]
    assert added == [True] * 10 + [False]
    assert bank.count("吃") == 10


def test_add_keeps_cards_order(files):
    path, _ = files
    write_bank(path, line("爸爸", B), line("我", A))
    bank = make(files)
    bank.add("饭", sentence(C), MODEL)
    bank.add("吃", sentence(A), MODEL)
    assert [r["id"] for r in rows(path)] == IDS


def test_add_keeps_lines_for_other_ids_unchanged(files):
    path, _ = files
    other = line("gone", D)
    write_bank(path, line("吃", A), other)
    make(files).add("吃", sentence(B), MODEL)
    assert json.loads(other) in rows(path)
    assert len(rows(path)) == 2


def test_add_never_shrinks_the_file(files):
    path, _ = files
    write_bank(path, line("爸爸", B), line("gone", D), line("吃", A, C))
    before = rows(path)
    make(files).add("饭", sentence(C), MODEL)
    after = rows(path)
    assert len(after) == len(before) + 1
    for row in before:
        assert row in after


def test_add_writes_atomically(files, monkeypatch):
    """A failed write leaves the old bank whole (temp file + swap), with no leftovers."""
    path, _ = files
    write_bank(path, line("吃", A))
    before = path.read_bytes()
    bank = make(files)
    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        bank.add("吃", sentence(B), MODEL)
    assert path.read_bytes() == before
    assert [p.name for p in path.parent.iterdir() if p.name.endswith(".part")] == []


# Failure modes


def test_missing_bank_is_an_empty_bank(files):
    bank = make(files)
    assert bank.count("吃") == 0
    assert bank.banked("吃") is None
    assert bank.chance_of_new("吃") == 1.0


def test_unreadable_bank_line_raises_naming_the_line(files):
    path, _ = files
    path.write_text(line("吃", A) + "\n" + '{"id": "饭"\n', encoding="utf-8")
    with pytest.raises(sentence_writer.SentenceFileError, match="line 2"):
        make(files)


def test_unreadable_bank_line_is_a_value_error(files):
    path, _ = files
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ValueError):
        make(files)


def test_same_id_on_two_lines_uses_the_first(files):
    path, _ = files
    write_bank(path, line("吃", A), line("吃", B, C))
    bank = make(files)
    assert bank.count("吃") == 1
    assert bank.banked("吃") == sentence(A)


def test_lines_for_other_ids_are_ignored(files):
    path, _ = files
    write_bank(path, line("gone", A, B, C, D))
    bank = make(files)
    assert all(bank.count(w) == 0 for w in IDS)


def test_missing_seen_file_means_nothing_seen(files):
    path, seen = files
    write_bank(path, line("吃", A, B))
    assert not seen.exists()
    assert make(files).banked("吃") == sentence(A)


@pytest.mark.parametrize(
    "bad",
    [
        "{not json",
        "[1, 2]",
        '{"吃": "yesterday"}',
        '{"吃": {"我吃饭。": "not a time"}}',
    ],
)
def test_unreadable_seen_file_warns_and_counts_as_nothing_seen(
    files, bad, capsys, caplog, recwarn
):
    path, seen = files
    write_bank(path, line("吃", A, B))
    seen.write_text(bad, encoding="utf-8")
    assert make(files).banked("吃") == sentence(A)
    captured = capsys.readouterr()
    warned = " ".join(str(w.message) for w in recwarn)
    assert "seen" in (captured.out + captured.err + caplog.text + warned).lower()


def test_unreadable_seen_file_is_rewritten_on_next_mark_seen(files):
    path, seen = files
    write_bank(path, line("吃", A, B))
    seen.write_text("{not json", encoding="utf-8")
    make(files).mark_seen("吃", sentence(B))
    data = json.loads(seen.read_text(encoding="utf-8"))
    assert set(data) == {"吃"}
    assert set(data["吃"]) == {B[0]}


@pytest.mark.parametrize(
    "call",
    [
        lambda b, w: b.count(w),
        lambda b, w: b.chance_of_new(w),
        lambda b, w: b.wants_new(w),
        lambda b, w: b.banked(w),
        lambda b, w: b.mark_seen(w, sentence(A)),
        lambda b, w: b.add(w, sentence(A), MODEL),
    ],
    ids=["count", "chance_of_new", "wants_new", "banked", "mark_seen", "add"],
)
@pytest.mark.parametrize("word", ["nope", "gone"])
def test_unknown_card_id_is_a_value_error(files, call, word):
    """ "gone" is in the bank file but not one of the cards: still not allowed."""
    path, _ = files
    write_bank(path, line("gone", A))
    bank = make(files)
    with pytest.raises(ValueError):
        call(bank, word)


@pytest.mark.parametrize(
    "settings", [{"floor": -0.1}, {"floor": 1.1}, {"cap": 0}, {"cap": -1}]
)
def test_bad_settings_are_rejected(settings):
    with pytest.raises(ValidationError):
        block.BankSettings(**settings)


def test_edge_settings_are_allowed():
    assert block.BankSettings(floor=0.0).floor == 0.0
    assert block.BankSettings(floor=1.0, cap=1).cap == 1


# -- block-review round 1 --------------------------------------------------------------


def test_mark_seen_for_a_sentence_not_in_the_bank_is_recorded(files):
    path, seen = files
    write_bank(path, line("吃", A))
    make(files).mark_seen("吃", sentence(E))
    assert E[0] in json.loads(seen.read_text(encoding="utf-8"))["吃"]


def test_add_keeps_a_second_copy_of_an_id_as_it_is(files):
    path, _ = files
    second = line("吃", B, C)
    write_bank(path, line("吃", A), second)
    assert make(files).add("吃", sentence(D), MODEL)
    assert second in path.read_text(encoding="utf-8").splitlines()


def test_cap_above_the_writers_limit_is_rejected():
    with pytest.raises(ValidationError):
        block.BankSettings(cap=11)


def test_seen_time_without_a_timezone_warns_and_counts_as_nothing_seen(files, capsys):
    path, seen = files
    write_bank(path, line("吃", A, B))
    seen.write_text(json.dumps({"吃": {A[0]: "2026-11-04T09:00"}}), encoding="utf-8")
    bank = make(files)
    assert "seen" in capsys.readouterr().out.lower()
    assert bank.banked("吃") == sentence(A)  # never seen first: no crash


# -- /code-review round 1 --------------------------------------------------------------


def test_two_quizzes_at_once_keep_both_histories(files):
    path, seen = files
    write_bank(path, line("吃", A, B), line("饭", C))
    first, second = make(files), make(files)  # both opened before either saves
    first.mark_seen("吃", sentence(A))
    second.mark_seen("饭", sentence(C))
    saved = json.loads(seen.read_text(encoding="utf-8"))
    assert A[0] in saved["吃"] and C[0] in saved["饭"]


# -- The removed list (ADR 0015) -------------------------------------------------------
# SPEC Inputs `removed_path`, Output 5, and the removed-list failure modes. These tests
# pass their own `removed_path` (a tmp file), so they never read the committed list.


@pytest.fixture
def removed(tmp_path):
    return tmp_path / "sentences_removed.json"


def make_r(files, removed, cards=DECK, settings=None, rng=None, now=None):
    """Like `make`, with a removed list in tmp_path."""
    path, seen = files
    return block.SentenceBank(
        cards,
        path=path,
        seen_path=seen,
        removed_path=removed,
        settings=settings or block.BankSettings(),
        rng=rng or random.Random(0),
        now=now or Clock(),
    )


def write_removed(removed, data: dict) -> None:
    removed.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def listed(removed) -> dict[str, list[str]]:
    return json.loads(removed.read_text(encoding="utf-8"))


def fail_replace_to(target: Path):
    """An os.replace that fails only when swapping into `target`."""
    real_replace = os.replace

    def replace(src, dst):
        if Path(dst) == target:
            raise OSError("disk full")
        return real_replace(src, dst)

    return replace


def test_default_removed_file_matches_spec():
    params = inspect.signature(block.SentenceBank).parameters
    assert params["removed_path"].default == block.REMOVED_FILE
    assert block.REMOVED_FILE.name == "sentences_removed.json"
    assert block.REMOVED_FILE.parent == sentence_writer.SENTENCES_FILE.parent
    assert block.REMOVED_FILE.parent.name == "generated"


def test_remove_lists_it_and_takes_it_out_of_the_bank(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B))
    bank = make_r(files, removed)
    assert bank.remove("吃", A[0]) is True
    assert listed(removed) == {"吃": [A[0]]}
    assert hanzi_of(path, "吃") == [B[0]]
    assert bank.is_removed("吃", A[0]) is True
    assert bank.count("吃") == 1  # this bank knows at once
    assert bank.banked("吃") == sentence(B)


def test_remove_drops_a_line_left_with_no_sentences(files, removed):
    path, _ = files
    write_bank(path, line("吃", A), line("饭", C))
    bank = make_r(files, removed)
    assert bank.remove("吃", A[0]) is True
    assert "吃" not in by_id(path)
    assert bank.count("吃") == 0
    assert bank.banked("吃") is None
    assert bank.chance_of_new("吃") == 1.0


def test_remove_keeps_other_words_and_other_lines(files, removed):
    """Matching is per word: the same hanzi under another word stays."""
    path, _ = files
    others = [line("爸爸", B), line("饭", A), line("gone", A, D)]
    write_bank(path, others[0], line("吃", A, C), others[1], others[2])
    bank = make_r(files, removed)
    bank.remove("吃", A[0])
    after = rows(path)
    for row in others:
        assert json.loads(row) in after
    assert len(after) == 4
    assert hanzi_of(path, "吃") == [C[0]]
    assert [r["id"] for r in after][:3] == ["爸爸", "吃", "饭"]  # cards order kept
    assert bank.is_removed("饭", A[0]) is False
    assert bank.count("饭") == 1


def test_remove_keeps_a_second_copy_of_an_id_as_it_is(files, removed):
    path, _ = files
    second = line("吃", A, C)
    write_bank(path, line("吃", A, B), second)
    make_r(files, removed).remove("吃", A[0])
    assert second in path.read_text(encoding="utf-8").splitlines()


def test_remove_of_a_sentence_not_in_the_bank_lists_it_and_returns_false(
    files, removed
):
    path, _ = files
    write_bank(path, line("吃", A))
    before = path.read_bytes()
    bank = make_r(files, removed)
    assert bank.remove("吃", E[0]) is False
    assert listed(removed) == {"吃": [E[0]]}
    assert bank.is_removed("吃", E[0]) is True
    assert path.read_bytes() == before


def test_removing_twice_does_nothing(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B))
    bank = make_r(files, removed)
    assert bank.remove("吃", A[0]) is True
    bank_before = path.read_bytes()
    assert bank.remove("吃", A[0]) is False
    assert listed(removed) == {"吃": [A[0]]}
    assert path.read_bytes() == bank_before
    assert make_r(files, removed).remove("吃", A[0]) is False  # a new bank too
    assert listed(removed) == {"吃": [A[0]]}


def test_remove_adds_to_an_existing_list(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B), line("饭", C))
    write_removed(removed, {"吃": [E[0]]})
    bank = make_r(files, removed)
    bank.remove("吃", A[0])
    bank.remove("饭", C[0])
    saved = listed(removed)
    assert sorted(saved["吃"]) == sorted([E[0], A[0]])
    assert saved["饭"] == [C[0]]


def test_remove_writes_the_list_before_the_bank(files, removed, monkeypatch):
    """If saving the bank fails, the sentence is already listed (so never shown)."""
    path, _ = files
    write_bank(path, line("吃", A, B))
    before = path.read_bytes()
    bank = make_r(files, removed)
    monkeypatch.setattr(os, "replace", fail_replace_to(path))
    with pytest.raises(OSError):
        bank.remove("吃", A[0])
    monkeypatch.undo()
    assert path.read_bytes() == before  # the bank is whole (atomic)
    assert listed(removed) == {"吃": [A[0]]}
    fresh = make_r(files, removed)
    assert fresh.count("吃") == 1  # still in the file, but skipped
    assert fresh.banked("吃") == sentence(B)


def test_remove_raises_when_the_list_cant_be_saved(files, removed, monkeypatch):
    path, _ = files
    write_bank(path, line("吃", A, B))
    before = path.read_bytes()
    bank = make_r(files, removed)
    monkeypatch.setattr(os, "replace", fail_replace_to(removed))
    with pytest.raises(OSError):
        bank.remove("吃", A[0])
    assert path.read_bytes() == before  # list first: the bank wasn't touched
    assert not removed.exists()


def test_add_refuses_a_listed_sentence_and_writes_nothing(files, removed):
    path, _ = files
    write_bank(path, line("吃", A))
    write_removed(removed, {"吃": [B[0]]})
    before = path.read_bytes()
    bank = make_r(files, removed)
    assert bank.add("吃", sentence(B), MODEL) is False
    assert path.read_bytes() == before
    assert bank.count("吃") == 1


def test_add_refuses_a_sentence_just_removed(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B))
    bank = make_r(files, removed)
    bank.remove("吃", A[0])
    before = path.read_bytes()
    assert bank.add("吃", sentence(A), MODEL) is False
    assert path.read_bytes() == before


def test_add_of_a_hanzi_listed_for_another_word_is_allowed(files, removed):
    path, _ = files
    write_removed(removed, {"饭": [A[0]]})
    assert make_r(files, removed).add("吃", sentence(A), MODEL) is True
    assert hanzi_of(path, "吃") == [A[0]]


def test_listed_sentences_still_in_the_file_are_skipped(files, removed):
    """E.g. written back by sentence_writer: count, chance and banked ignore them."""
    path, _ = files
    write_bank(path, line("吃", A, B, C))
    write_removed(removed, {"吃": [A[0]]})
    before = path.read_bytes()
    bank = make_r(files, removed)
    assert bank.count("吃") == 2
    assert bank.chance_of_new("吃") == pytest.approx(1 / 3)
    assert bank.banked("吃") == sentence(B)
    assert path.read_bytes() == before  # the file isn't changed just for that


def test_listed_sentence_is_never_banked_even_when_never_seen(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B))
    write_removed(removed, {"吃": [A[0]]})
    bank = make_r(files, removed)
    bank.mark_seen("吃", sentence(B))  # A is "never seen", B seen: B still wins
    assert bank.banked("吃") == sentence(B)


def test_a_word_whose_sentences_are_all_listed_has_none(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B))
    write_removed(removed, {"吃": [A[0], B[0]]})
    bank = make_r(files, removed)
    assert bank.count("吃") == 0
    assert bank.banked("吃") is None
    assert bank.chance_of_new("吃") == 1.0
    assert bank.wants_new("吃") is True


def test_a_new_bank_reads_the_list_back(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B), line("饭", C))
    make_r(files, removed).remove("吃", A[0])
    write_bank(path, line("吃", A, B), line("饭", C))  # e.g. written back
    bank = make_r(files, removed)
    assert bank.is_removed("吃", A[0]) is True
    assert bank.is_removed("吃", B[0]) is False
    assert bank.is_removed("饭", A[0]) is False
    assert bank.count("吃") == 1


def test_is_removed_reads_a_list_on_disk(files, removed):
    write_removed(removed, {"吃": [A[0], B[0]], "饭": [C[0]]})
    bank = make_r(files, removed)
    assert bank.is_removed("吃", B[0]) is True
    assert bank.is_removed("饭", C[0]) is True
    assert bank.is_removed("饭", A[0]) is False
    assert bank.is_removed("我", A[0]) is False


def test_missing_removed_list_means_nothing_removed(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B))
    bank = make_r(files, removed)
    assert bank.is_removed("吃", A[0]) is False
    assert bank.count("吃") == 2
    assert bank.banked("吃") == sentence(A)
    assert not removed.exists()  # making a bank doesn't create the list


def test_listed_ids_that_are_not_cards_are_allowed(files, removed):
    """The list may name ids that are no longer cards: not a broken list."""
    write_removed(removed, {"gone": [A[0]]})
    assert make_r(files, removed).count("吃") == 0


@pytest.mark.parametrize(
    "bad",
    [
        "{not json",
        "[1, 2]",
        '"我吃饭。"',
        '{"吃": "我吃饭。"}',
        '{"吃": [1]}',
        '{"吃": {"我吃饭。": true}}',
    ],
)
def test_broken_removed_list_raises_naming_the_file(files, removed, bad):
    removed.write_text(bad, encoding="utf-8")
    with pytest.raises(sentence_writer.SentenceFileError, match=removed.name):
        make_r(files, removed)


def test_broken_removed_list_is_a_value_error(files, removed):
    removed.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        make_r(files, removed)


@pytest.mark.parametrize(
    "call",
    [
        lambda b, w: b.is_removed(w, A[0]),
        lambda b, w: b.remove(w, A[0]),
    ],
    ids=["is_removed", "remove"],
)
@pytest.mark.parametrize("word", ["nope", "gone"])
def test_unknown_card_id_is_a_value_error_for_the_removed_list(
    files, removed, call, word
):
    """ "gone" is in the bank file but not one of the cards; nothing is written."""
    path, _ = files
    write_bank(path, line("gone", A))
    before = path.read_bytes()
    bank = make_r(files, removed)
    with pytest.raises(ValueError):
        call(bank, word)
    assert path.read_bytes() == before
    assert not removed.exists()


# -- Removed list: the SPEC's "Small rules" (Output 5) ---------------------------------


def test_add_drops_listed_sentences_still_in_the_line(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B))
    write_removed(removed, {"吃": [A[0]]})
    assert make_r(files, removed).add("吃", sentence(C), MODEL) is True
    assert hanzi_of(path, "吃") == [B[0], C[0]]
    assert listed(removed) == {"吃": [A[0]]}


def test_cap_counts_only_usable_sentences(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B))
    write_removed(removed, {"吃": [A[0]]})
    bank = make_r(files, removed, settings=block.BankSettings(cap=2))
    assert bank.add("吃", sentence(C), MODEL) is True
    assert hanzi_of(path, "吃") == [B[0], C[0]]
    assert bank.add("吃", sentence(D), MODEL) is False  # now really full


def test_add_never_grows_a_line_past_the_cap(files, removed):
    path, _ = files
    ten = [(f"吃{i}。", f"chī {i}。", f"Eat {i}.") for i in range(10)]
    write_bank(path, line("吃", *ten))
    write_removed(removed, {"吃": [ten[3][0]]})
    assert make_r(files, removed).add("吃", sentence(E), MODEL) is True
    saved = hanzi_of(path, "吃")
    assert len(saved) == 10 == sentence_writer.MAX_SAVED
    assert ten[3][0] not in saved and saved[-1] == E[0]


def test_remove_of_a_listed_sentence_still_in_the_file_takes_it_out(files, removed):
    """It was already out of use, so not "in the bank": returns False."""
    path, _ = files
    write_bank(path, line("吃", A, B))
    write_removed(removed, {"吃": [A[0]]})
    assert make_r(files, removed).remove("吃", A[0]) is False
    assert hanzi_of(path, "吃") == [B[0]]
    assert listed(removed) == {"吃": [A[0]]}


def test_remove_of_the_last_listed_sentence_in_the_file_drops_the_line(files, removed):
    path, _ = files
    write_bank(path, line("吃", A), line("饭", C))
    write_removed(removed, {"吃": [A[0]]})
    assert make_r(files, removed).remove("吃", A[0]) is False
    assert "吃" not in by_id(path)
    assert hanzi_of(path, "饭") == [C[0]]


def test_remove_with_no_bank_file_only_writes_the_list(files, removed):
    path, _ = files
    assert make_r(files, removed).remove("吃", A[0]) is False
    assert listed(removed) == {"吃": [A[0]]}
    assert not path.exists()


def test_remove_keeps_listed_ids_that_are_not_cards(files, removed):
    path, _ = files
    write_bank(path, line("吃", A, B))
    write_removed(removed, {"gone": [D[0]]})
    make_r(files, removed).remove("吃", A[0])
    assert listed(removed) == {"gone": [D[0]], "吃": [A[0]]}


def test_remove_keeps_a_removal_made_meanwhile_by_another_bank(files, removed):
    """Code review: `remove` merges with the list on disk, so two banks (an audit
    and a quiz, or two audits) don't lose each other's removals."""
    path, _ = files
    write_bank(path, line("吃", A, B), line("饭", C))
    first = make_r(files, removed)
    second = make_r(files, removed)
    second.remove("饭", C[0])
    first.remove("吃", A[0])
    assert json.loads(removed.read_text(encoding="utf-8")) == {
        "饭": [C[0]],
        "吃": [A[0]],
    }
    assert first.is_removed("饭", C[0])  # it read the other's removal back
