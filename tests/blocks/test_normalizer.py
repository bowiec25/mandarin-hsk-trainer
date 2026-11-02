"""Tests for the normalizer block: contract (ID card + SPEC) and behaviour (from SPEC.md)."""

import inspect
import json
from pathlib import Path

import pytest

import hsk_trainer.blocks.normalizer as block
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.models import Card

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "normalizer"
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


# ---- Behaviour (from SPEC.md), using small fake raw files in tmp_path -----------------
# Assumed interface (SPEC names the inputs, not the function): run(src=..., dest=...)
# returns list[Card], and every error is block.NormalizeError.


def form(pinyin: str, meanings: list[str]) -> dict:
    return {
        "traditional": "X",
        "transcriptions": {"pinyin": pinyin, "numeric": "x1"},
        "meanings": meanings,
        "classifiers": [],
    }


def word(simplified: str, forms: list[dict], pos: list[str] | None = None) -> dict:
    return {
        "simplified": simplified,
        "radical": "口",
        "frequency": 1,
        "pos": pos if pos is not None else ["n"],
        "forms": forms,
    }


AI = word(
    "爱",
    [
        form(
            "ài",
            [
                "to love; to be fond of; to like",
                "affection",
                "to be inclined (to do sth); to tend to (happen)",
            ],
        )
    ],
    pos=["v", "vn", "b"],
)
BA = word(
    "吧",
    [
        form("bā", ["bar (loanword)", "(onom.) bang"]),
        form("ba", ["(modal particle indicating suggestion or surmise)", "...OK?"]),
        form("biā", ["(onom.) smack!"]),
    ],
    pos=["y"],
)
HAO = word("好", [form("hǎo", ["good"])], pos=["a"])
SHUO = word("说", [form("shuō", ["to speak"])], pos=["v"])

DEFAULT_BANDS = {1: [AI, BA], 2: [HAO], 3: [SHUO]}


def write_raw(folder: Path, bands: dict[int, list[dict]] | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for band, words in (bands or DEFAULT_BANDS).items():
        (folder / f"{band}.json").write_text(
            json.dumps(words, ensure_ascii=False), encoding="utf-8"
        )
    return folder


def normalize(tmp_path: Path, bands=None, dest: Path | None = None) -> list[Card]:
    src = write_raw(tmp_path / "raw", bands)
    return block.run(src=src, dest=dest or tmp_path / "out" / "cards.jsonl")


def only_band_1(*words: dict) -> dict[int, list[dict]]:
    return {1: list(words), 2: [], 3: []}


def by_id(cards: list[Card]) -> dict[str, Card]:
    return {c.id: c for c in cards}


# -- Outputs --


def test_default_paths_match_spec():
    params = inspect.signature(block.run).parameters
    assert Path(params["src"].default) == Path("data/raw/hsk3_2026")
    assert Path(params["dest"].default) == Path("data/processed/cards.jsonl")


def test_returns_one_card_per_word_in_band_then_file_order(tmp_path):
    cards = normalize(tmp_path)
    assert all(isinstance(c, Card) for c in cards)
    assert [(c.id, c.level) for c in cards] == [
        ("爱", 1),
        ("吧", 1),
        ("好", 2),
        ("说", 3),
    ]


def test_single_reading_card_shape(tmp_path):
    ai = by_id(normalize(tmp_path))["爱"]
    assert ai.id == "爱"
    assert ai.level == 1
    assert ai.fields == {
        "hanzi": "爱",
        "pinyin": "ài",
        "pos": "v, vn, b",
        "readings": "1",
    }
    assert ai.answers == [
        "to love",
        "to be fond of",
        "to like",
        "affection",
        "to be inclined (to do sth)",
        "to tend to (happen)",
    ]


def test_multi_reading_pinyin_joined_and_all_meanings_kept(tmp_path):
    ba = by_id(normalize(tmp_path))["吧"]
    assert ba.fields["pinyin"] == "bā / ba / biā"
    assert ba.fields["readings"] == "3"
    assert ba.fields["pos"] == "y"
    assert ba.answers == [
        "bar (loanword)",
        "(onom.) bang",
        "(modal particle indicating suggestion or surmise)",
        "...OK?",
        "(onom.) smack!",
    ]


def test_repeated_pinyin_counted_once_order_kept(tmp_path):
    w = word("得", [form("de", ["a"]), form("dé", ["b"]), form("de", ["c"])])
    card = normalize(tmp_path, only_band_1(w))[0]
    assert card.fields["pinyin"] == "de / dé"
    assert card.fields["readings"] == "2"


def test_semicolon_inside_brackets_is_not_split(tmp_path):
    w = word("行", [form("xíng", ["OK (lit.; fig.); to walk", "fine [a; b]"])])
    card = normalize(tmp_path, only_band_1(w))[0]
    assert card.answers == ["OK (lit.; fig.)", "to walk", "fine [a; b]"]


def test_answers_trimmed_and_repeats_removed(tmp_path):
    w = word(
        "看", [form("kàn", ["  to see ;to look", "to see"]), form("kān", ["to look"])]
    )
    card = normalize(tmp_path, only_band_1(w))[0]
    assert card.answers == ["to see", "to look"]


def test_extra_raw_fields_are_ignored(tmp_path):
    ai = by_id(normalize(tmp_path))["爱"]
    assert set(ai.fields) == {"hanzi", "pinyin", "pos", "readings"}


def test_file_is_one_card_per_line_utf8_readable(tmp_path):
    dest = tmp_path / "out" / "cards.jsonl"
    cards = normalize(tmp_path, dest=dest)
    text = dest.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert len(lines) == len(cards) == 4
    assert "爱" in text and "\\u" not in text  # Chinese kept readable
    assert [Card.model_validate_json(line) for line in lines] == cards


def test_same_input_gives_byte_identical_file(tmp_path):
    dest = tmp_path / "out" / "cards.jsonl"
    normalize(tmp_path, dest=dest)
    first = dest.read_bytes()
    normalize(tmp_path, dest=dest)
    assert dest.read_bytes() == first


# -- Failure modes --


def test_creates_missing_output_folder(tmp_path):
    dest = tmp_path / "deep" / "new" / "cards.jsonl"
    normalize(tmp_path, dest=dest)
    assert dest.exists()


def test_missing_raw_file_raises_error_naming_file(tmp_path):
    dest = tmp_path / "out" / "cards.jsonl"
    with pytest.raises(block.NormalizeError, match=r"2\.json"):
        normalize(tmp_path, {1: [AI], 3: [SHUO]}, dest=dest)
    assert not dest.exists()


def test_invalid_json_raises_error_naming_file(tmp_path):
    src = write_raw(tmp_path / "raw")
    (src / "3.json").write_text("[{not json", encoding="utf-8")
    dest = tmp_path / "out" / "cards.jsonl"
    with pytest.raises(block.NormalizeError, match=r"3\.json"):
        block.run(src=src, dest=dest)
    assert not dest.exists()


@pytest.mark.parametrize(
    "bad",
    [
        word("", [form("hǎo", ["good"])]),
        word("坏", [form("", ["bad"])]),
        word("坏", [form("huài", [])]),
        word("坏", [form("huài", ["  "])]),
        word("坏", []),
        word("坏", [form("huài", ["bad"]), form(" ", ["x"])]),
    ],
    ids=[
        "no-characters",
        "no-pinyin",
        "no-meanings",
        "blank-meanings",
        "no-forms",
        "one-reading-blank-pinyin",
    ],
)
def test_word_missing_data_raises_error_naming_word_and_band(tmp_path, bad):
    dest = tmp_path / "out" / "cards.jsonl"
    with pytest.raises(block.NormalizeError) as err:
        normalize(tmp_path, {1: [AI], 2: [bad], 3: [SHUO]}, dest=dest)
    msg = str(err.value)
    assert "band 2" in msg and "2.json" in msg
    if bad["simplified"]:
        assert "坏" in msg
    assert not dest.exists()


@pytest.mark.parametrize(
    "bad",
    [
        word("坏", [{"meanings": ["bad"]}]),  # no transcriptions key
        word("坏", [{"transcriptions": {"pinyin": "huài"}}]),  # no meanings key
        word("坏", [form("huài", "bad")]),  # meanings is text, not a list
        word("坏", [form(None, ["bad"])]),  # pinyin is null
        word("坏", [form("huài", [None])]),  # a meaning is null
        word("坏", [form("huài", ["bad"])], pos="vn"),  # pos is text, not a list
        {**word("坏", [form("huài", ["bad"])]), "pos": None},  # pos is null
        {k: v for k, v in word("坏", [form("huài", ["bad"])]).items() if k != "pos"},
    ],
    ids=[
        "no-transcriptions",
        "no-meanings-key",
        "meanings-text",
        "pinyin-null",
        "meaning-null",
        "pos-text",
        "pos-null",
        "pos-missing",
    ],
)
def test_wrong_shaped_word_raises_error_naming_word_and_band(tmp_path, bad):
    """Bad data never slips through silently (no letters-as-answers, no 'None')."""
    dest = tmp_path / "out" / "cards.jsonl"
    with pytest.raises(block.NormalizeError, match=r"2\.json.*坏.*band 2"):
        normalize(tmp_path, {1: [AI], 2: [bad], 3: [SHUO]}, dest=dest)
    assert not dest.exists()


def test_save_failure_raises_normalize_error(tmp_path, monkeypatch):
    """Disk full / no permission → a clear NormalizeError, not a raw OSError."""

    def disk_full(dest, data):
        raise OSError("disk full")

    monkeypatch.setattr(block, "write_atomically", disk_full)
    with pytest.raises(block.NormalizeError, match="cards.jsonl"):
        normalize(tmp_path)


def test_output_folder_cannot_be_made_raises_normalize_error(tmp_path):
    """mkdir fails (a file sits where the folder should be) → NormalizeError."""
    blocker = tmp_path / "out"
    blocker.write_text("not a folder", encoding="utf-8")
    with pytest.raises(block.NormalizeError, match="cards.jsonl"):
        normalize(tmp_path, dest=blocker / "cards.jsonl")


def test_non_utf8_file_raises_error_naming_file(tmp_path):
    src = write_raw(tmp_path / "raw")
    (src / "1.json").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(block.NormalizeError, match=r"1\.json"):
        block.run(src=src, dest=tmp_path / "out" / "cards.jsonl")


def test_raw_file_not_a_list_raises_error_naming_file(tmp_path):
    src = write_raw(tmp_path / "raw")
    (src / "2.json").write_text('{"simplified": "好"}', encoding="utf-8")
    dest = tmp_path / "out" / "cards.jsonl"
    with pytest.raises(block.NormalizeError, match=r"2\.json"):
        block.run(src=src, dest=dest)
    assert not dest.exists()


def test_empty_pos_is_allowed(tmp_path):
    """11 real words have no part of speech: that's fine, pos is just blank."""
    card = normalize(tmp_path, only_band_1(word("嗯", [form("ng", ["hmm"])], pos=[])))[
        0
    ]
    assert card.fields["pos"] == ""


def test_duplicate_word_in_one_band_raises_error(tmp_path):
    with pytest.raises(block.NormalizeError, match=r"1\.json.*好.*band 1"):
        normalize(tmp_path, only_band_1(HAO, HAO))


def test_duplicate_word_across_bands_raises_error(tmp_path):
    with pytest.raises(block.NormalizeError, match=r"3\.json.*好.*band 3"):
        normalize(tmp_path, {1: [HAO], 2: [AI], 3: [HAO]})


def test_failure_leaves_old_good_file_untouched(tmp_path):
    """Write-to-temp-then-swap: an old good file survives, no temp file left behind."""
    dest = tmp_path / "out" / "cards.jsonl"
    normalize(tmp_path, dest=dest)
    good = dest.read_bytes()
    with pytest.raises(block.NormalizeError):
        normalize(tmp_path, {1: [HAO], 2: [HAO], 3: []}, dest=dest)
    assert dest.read_bytes() == good
    assert [p.name for p in dest.parent.iterdir()] == ["cards.jsonl"]
