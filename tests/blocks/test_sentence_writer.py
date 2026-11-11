"""Tests for the sentence_writer block: contract (ID card + SPEC) and behaviour (from SPEC.md)."""

import inspect
import json
from pathlib import Path

import pytest

import hsk_trainer.blocks.sentence_writer as block
from hsk_trainer.blocks.sentence_validator import Vocab, check_sentence
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.models import Card

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "sentence_writer"
    assert block.BLOCK_SPEC.kind == "agent"


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


# ---- Behaviour (from SPEC.md), with a fake Claude --------------------------------
# The block's public names are reached through `block.` (not imported at the top), so
# the contract tests above still run while the block is only a stub. The checker is
# the real sentence_validator, so the toy sentences below genuinely pass or fail it.

SENTENCES_JSONL = Path(__file__).parents[2] / "data" / "generated" / "sentences.jsonl"
FAKE_MODEL = "fake-sonnet"
NEXT = "next"  # a prompt version bump in tests


def card(hanzi, pinyin, level, meanings, readings="1") -> Card:
    return Card(
        id=hanzi,
        fields={"hanzi": hanzi, "pinyin": pinyin, "readings": readings},
        answers=meanings,
        level=level,
    )


# Cards order (like cards.jsonl): bands mixed, 一起 (band 2) in the middle.
DECK = [
    card("爸爸", "bà ba", 1, ["father", "dad"]),
    card("吃", "chī", 1, ["to eat"]),
    card("饭", "fàn", 1, ["meal"]),
    card("我", "wǒ", 1, ["I", "me"]),
    card("一起", "yī qǐ", 2, ["together"]),
    card("我们", "wǒ men", 1, ["we", "us"]),
    card("是", "shì", 1, ["to be"]),
    card("医生", "yī shēng", 1, ["doctor"]),
]
BAND1 = [c for c in DECK if c.level == 1]
IDS = [c.id for c in DECK]
BAND1_IDS = [c.id for c in BAND1]

# Claude's pinyin for each toy sentence (deck: 爸爸 bà ba, 吃 chī, 饭 fàn, 我 wǒ,
# 一起 yī qǐ, 我们 wǒ men, 是 shì, 医生 yī shēng).
PINYIN = {
    "我爸爸是医生。": "wǒ bà ba shì yī shēng",
    "爸爸吃饭。": "bà ba chī fàn",
    "我吃饭。": "wǒ chī fàn",
    "我们吃饭。": "wǒ men chī fàn",
    "我是医生。": "wǒ shì yī shēng",
    "我们一起吃饭。": "wǒ men yī qǐ chī fàn",
    "我们是医生。": "wǒ men shì yī shēng",
    "爸爸是医生。": "bà ba shì yī shēng",
}


def s(hanzi: str, english: str) -> tuple[str, str, str]:
    """A toy sentence as Claude sends it: (hanzi, pinyin, english)."""
    return (hanzi, PINYIN[hanzi], english)


GOOD = {
    "爸爸": [s("我爸爸是医生。", "My dad is a doctor."), s("爸爸吃饭。", "Dad eats.")],
    "吃": [s("我吃饭。", "I eat."), s("爸爸吃饭。", "Dad eats.")],
    "饭": [s("我吃饭。", "I eat."), s("我们吃饭。", "We eat.")],
    "我": [s("我是医生。", "I am a doctor."), s("我吃饭。", "I eat.")],
    "一起": [s("我们一起吃饭。", "We eat together.")],
    "我们": [s("我们吃饭。", "We eat."), s("我们是医生。", "We are doctors.")],
    "是": [s("我是医生。", "I am a doctor."), s("爸爸是医生。", "Dad is a doctor.")],
    "医生": [
        s("我爸爸是医生。", "My dad is a doctor."),
        s("我是医生。", "I am a doctor."),
    ],
}
# Fails the checker for 吃 or 饭 (band 1): it uses 一起 (band 2). Its pinyin is right.
BAD = s("我们一起吃饭。", "We eat together.")
# A band-1 word with several readings, for the "Claude's reading is kept" tests.
CHEAP = card("便宜", "biàn yí / pián yi", 1, ["cheap"], readings="2")


def items(triples) -> list[dict]:
    """Reply items in the SPEC shape: {"hanzi", "pinyin", "english"}."""
    return [{"hanzi": h, "pinyin": p, "english": e} for h, p, e in triples]


def reply(text: str):
    from quizkit.claude import ClaudeReply

    return ClaudeReply(
        text=text, model=FAKE_MODEL, input_tokens=100, output_tokens=50, cost_usd=0.01
    )


def claude_error(msg: str = "usage limit reached"):
    from quizkit.claude import ClaudeError

    return ClaudeError(msg)


class FakeClaude:
    """Replies with sentences for every deck word (the block ignores extras); records
    each prompt.

    The prompt lists every allowed word, so the fake can't tell which words were asked;
    it always answers for all of them. `sentences` overrides a word's sentences for
    every call (None = leave the word out); `script` maps call number (0-based) to a raw
    reply text, an exception to raise, or a dict of per-word overrides for that call.
    """

    def __init__(self, deck=DECK, sentences=None, script=None, extra=()):
        self.deck = deck
        self.sentences = {**GOOD, **(sentences or {})}
        self.script = script or {}
        self.extra = list(extra)
        self.prompts: list[str] = []

    def __call__(self, prompt: str, **kwargs):
        call = len(self.prompts)
        self.prompts.append(prompt)
        scripted = self.script.get(call)
        if isinstance(scripted, BaseException):
            raise scripted
        if isinstance(scripted, str):
            return reply(scripted)
        table = {**self.sentences, **(scripted or {})}
        ids = [c.id for c in self.deck if table.get(c.id) is not None] + self.extra
        body = {
            "cards": [
                {
                    "id": i,
                    "sentences": items(table[i]),
                }
                for i in ids
            ]
        }
        return reply(json.dumps(body, ensure_ascii=False))


def run(tmp_path, cards, ask, **kwargs):
    """SPEC: `cards` is the whole deck (it's also the checker's word list); a trial
    uses `limit`, not a smaller deck. The removed list defaults to a missing tmp
    file, so no test reads the committed one (block-reviewer)."""
    kwargs.setdefault("removed", tmp_path / "removed.json")
    return block.write_sentences(
        cards,
        ask=ask,
        out=tmp_path / "sentences.jsonl",
        log=tmp_path / "log.jsonl",
        **kwargs,
    )


def run_allowing_stop(tmp_path, cards, ask, **kwargs):
    """SPEC: on a Claude error, work so far is saved, then the ClaudeError goes up."""
    from quizkit.claude import ClaudeError

    with pytest.raises(ClaudeError):
        run(tmp_path, cards, ask, **kwargs)


def saved(tmp_path) -> list[dict]:
    path = tmp_path / "sentences.jsonl"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(t) for t in text.splitlines() if t.strip()]


def saved_ids(tmp_path) -> list[str]:
    return [row["id"] for row in saved(tmp_path)]


def saved_by_id(tmp_path) -> dict[str, dict]:
    return {row["id"]: row for row in saved(tmp_path)}


def kept(tmp_path, word) -> list[str]:
    return [s["hanzi"] for s in saved_by_id(tmp_path)[word]["sentences"]]


def log_entries(tmp_path) -> list[dict]:
    text = (tmp_path / "log.jsonl").read_text(encoding="utf-8")
    return [json.loads(t) for t in text.splitlines() if t.strip()]


def saved_line(word, sentences, version=None) -> str:
    return json.dumps(
        {
            "id": word,
            "hanzi": word,
            "sentences": [
                {"hanzi": h, "pinyin": laid_out(h, p), "english": e}
                for h, p, e in sentences
            ],
            "model": FAKE_MODEL,
            "prompt_version": version or str(block.PROMPT_VERSION),
        },
        ensure_ascii=False,
    )


def write_saved(tmp_path, *rows):
    text = "".join(r + "\n" for r in rows)
    (tmp_path / "sentences.jsonl").write_text(text, encoding="utf-8")


def laid_out(hanzi: str, pinyin: str) -> str:
    """The toy pinyin as the SPEC saves it: the sentence's end mark, no space before."""
    end = hanzi[-1] if hanzi[-1] in "。！？" else ""
    return pinyin if pinyin.endswith(end) else pinyin + end


def words_of(hanzi: str, word: str, cards=DECK) -> tuple[str, ...]:
    """The checker's word-by-word reading, the `words` pinyin_problems takes."""
    return check_sentence(hanzi, word, Vocab(cards)).words


def test_toy_sentences_really_pass_or_fail_the_checker():
    """Guard for the test data itself: GOOD passes the real checker, BAD fails."""
    vocab = Vocab(DECK)
    for word, triples in GOOD.items():
        for hanzi, _, _ in triples:
            assert check_sentence(hanzi, word, vocab).passed, (word, hanzi)
    assert not check_sentence(BAD[0], "吃", vocab).passed
    assert not check_sentence(BAD[0], "饭", vocab).passed
    assert check_sentence("饭便宜。", "便宜", Vocab([*DECK, CHEAP])).passed


def test_toy_pinyin_really_passes_the_pinyin_check():
    """Guard for the test data itself: every toy sentence's pinyin is right."""
    for word, triples in GOOD.items():
        for hanzi, pinyin, _ in triples:
            words = words_of(hanzi, word)
            assert block.pinyin_problems(hanzi, pinyin, words, DECK) == [], hanzi


# Public names and defaults (SPEC "How it's called")


def test_public_constants_match_spec():
    assert block.PROMPT_VERSION == "2"
    assert block.SENTENCES_FILE.name == "sentences.jsonl"
    assert block.SENTENCES_FILE.parent.name == "generated"
    assert block.LOG_FILE.name == "sentence_writer_log.jsonl"


def test_write_sentences_defaults_match_spec():
    from quizkit.claude import ask_claude

    params = inspect.signature(block.write_sentences).parameters
    assert params["limit"].default is None
    assert params["dry_run"].default is False
    assert params["chunk_size"].default == 20
    assert params["retries"].default == 2
    assert params["ask"].default is ask_claude
    assert params["out"].default == block.SENTENCES_FILE
    assert params["log"].default == block.LOG_FILE


# Output 1: sentences.jsonl


def test_good_reply_writes_one_line_per_word_with_spec_fields(tmp_path):
    run(tmp_path, DECK, FakeClaude())
    first = saved_by_id(tmp_path)["爸爸"]
    assert set(first) >= {"id", "hanzi", "sentences", "model", "prompt_version"}
    assert first["hanzi"] == "爸爸"
    assert first["model"] == FAKE_MODEL
    assert str(first["prompt_version"]) == block.PROMPT_VERSION
    assert [s["hanzi"] for s in first["sentences"]] == ["我爸爸是医生。", "爸爸吃饭。"]
    assert first["sentences"][0]["english"] == "My dad is a doctor."


def test_saved_sentence_has_claudes_pinyin_laid_out(tmp_path):
    """SPEC example: 我爸爸是医生。 → wǒ bà ba shì yī shēng。"""
    run(tmp_path, DECK, FakeClaude())
    pinyin = saved_by_id(tmp_path)["爸爸"]["sentences"][0]["pinyin"]
    assert pinyin == "wǒ bà ba shì yī shēng。"


def test_lines_saved_in_cards_order(tmp_path):
    run(tmp_path, DECK, FakeClaude())
    assert saved_ids(tmp_path) == IDS


def test_every_saved_sentence_passes_the_checker(tmp_path):
    run(tmp_path, DECK, FakeClaude(sentences={"吃": [BAD, GOOD["吃"][0]]}))
    vocab = Vocab(DECK)
    for row in saved(tmp_path):
        assert 1 <= len(row["sentences"]) <= 2
        for one in row["sentences"]:
            assert check_sentence(one["hanzi"], row["hanzi"], vocab).passed


def test_saved_after_every_claude_call(tmp_path):
    """If Claude stops on call 3, the words from calls 1 and 2 are already on disk."""
    fake = FakeClaude(BAND1, script={2: claude_error()})
    run_allowing_stop(tmp_path, BAND1, fake, chunk_size=2)
    assert saved_ids(tmp_path) == BAND1_IDS[:4]


def test_chunk_size_sets_words_per_call(tmp_path):
    run(tmp_path, BAND1, FakeClaude(BAND1), chunk_size=3)
    assert [e["cards"] for e in log_entries(tmp_path)] == [3, 3, 1]


# Output 2: the log


def test_log_has_one_line_per_call_with_spec_fields(tmp_path):
    run(tmp_path, BAND1, FakeClaude(BAND1), chunk_size=4)
    entries = log_entries(tmp_path)
    assert len(entries) == 2
    for entry, n in zip(entries, [4, 3], strict=True):
        assert entry["time"]
        assert entry["model"] == FAKE_MODEL
        assert entry["prompt_version"] == block.PROMPT_VERSION
        assert entry["cards"] == n
        assert entry["retry"] == 0
        assert (entry["input_tokens"], entry["output_tokens"]) == (100, 50)
        assert entry["cost_usd"] == pytest.approx(0.01)


def test_log_records_retry_round(tmp_path):
    fake = FakeClaude(BAND1, sentences={"吃": [BAD]}, script={1: {"吃": GOOD["吃"]}})
    run(tmp_path, BAND1, fake)
    entries = log_entries(tmp_path)
    assert [e["retry"] for e in entries] == [0, 1]
    assert [e["cards"] for e in entries] == [7, 1]


def test_log_grows_across_runs(tmp_path):
    run(tmp_path, BAND1, FakeClaude(BAND1), limit=2)
    run(tmp_path, BAND1, FakeClaude(BAND1))
    assert len(log_entries(tmp_path)) == 2


# Output 3: the summary


def test_summary_counts_written_skipped_failed_and_tokens(tmp_path):
    result = run(tmp_path, BAND1, FakeClaude(BAND1), chunk_size=4)
    assert result.written == 7
    assert result.skipped == 0
    assert list(result.failed) == []
    assert result.input_tokens == 200  # 2 calls x 100
    assert result.output_tokens == 100
    assert isinstance(result, block.SentenceRun)


def test_summary_printed_on_screen(tmp_path, capsys):
    run(tmp_path, BAND1[:2], FakeClaude(BAND1))
    assert "written" in capsys.readouterr().out


# The prompt: one band per call, with that band's allowed words


def test_one_band_per_call(tmp_path):
    fake = FakeClaude()
    run(tmp_path, DECK, fake)
    assert sorted(e["cards"] for e in log_entries(tmp_path)) == [1, 7]
    assert len(fake.prompts) == 2
    assert sum("一起" in p for p in fake.prompts) == 1  # never in the band-1 prompt


def test_band1_prompt_lists_all_band1_words_but_no_harder_ones(tmp_path):
    fake = FakeClaude()
    run(tmp_path, DECK, fake, limit=1)  # only 爸爸 is asked about
    (prompt,) = fake.prompts
    for word in BAND1_IDS:
        assert word in prompt
    assert "一起" not in prompt


def test_band2_prompt_lists_band1_and_band2_words(tmp_path):
    write_saved(tmp_path, *[saved_line(w, GOOD[w]) for w in BAND1_IDS])
    fake = FakeClaude()
    run(tmp_path, DECK, fake)
    (prompt,) = fake.prompts  # only 一起 still needs sentences
    for word in IDS:
        assert word in prompt


def test_prompt_shows_the_words_pinyin_and_meanings(tmp_path):
    fake = FakeClaude()
    run(tmp_path, DECK, fake, limit=1)
    assert "bà ba" in fake.prompts[0]
    assert "father" in fake.prompts[0]


# Retries


def test_failing_sentence_is_retried_with_its_reasons(tmp_path):
    fake = FakeClaude(BAND1, sentences={"吃": [BAD]}, script={1: {"吃": GOOD["吃"]}})
    result = run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 2
    retry = fake.prompts[1]
    assert BAD[0] in retry
    for reason in check_sentence(BAD[0], "吃", Vocab(BAND1)).reasons:
        assert reason in retry
    assert result.written == 7
    assert kept(tmp_path, "吃") == ["我吃饭。", "爸爸吃饭。"]


def test_retry_is_one_call_per_band_per_round(tmp_path):
    fake = FakeClaude(
        BAND1,
        sentences={"吃": [BAD], "饭": [BAD]},
        script={1: {"吃": GOOD["吃"], "饭": GOOD["饭"]}},
    )
    run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 2
    assert [e["cards"] for e in log_entries(tmp_path)] == [7, 2]


def test_still_failing_after_retries_is_failed_and_not_written(tmp_path):
    fake = FakeClaude(BAND1, sentences={"吃": [BAD]})
    result = run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 3  # first try + 2 retries (default)
    assert list(result.failed) == ["吃"]
    assert result.written == 6
    assert "吃" not in saved_ids(tmp_path)


@pytest.mark.parametrize("retries", [0, 1])
def test_retries_sets_extra_tries(tmp_path, retries):
    fake = FakeClaude(BAND1, sentences={"吃": [BAD]})
    result = run(tmp_path, BAND1, fake, retries=retries)
    assert len(fake.prompts) == 1 + retries
    assert list(result.failed) == ["吃"]


def test_partly_good_word_keeps_the_passing_sentence_without_retry(tmp_path):
    fake = FakeClaude(BAND1, sentences={"吃": [BAD, s("我吃饭。", "I eat.")]})
    result = run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 1
    assert list(result.failed) == []
    assert kept(tmp_path, "吃") == ["我吃饭。"]


def test_more_than_two_sentences_keeps_the_first_two_that_pass(tmp_path):
    many = [
        BAD,
        s("我吃饭。", "I eat."),
        s("爸爸吃饭。", "Dad eats."),
        s("我们吃饭。", "We eat."),
    ]
    run(tmp_path, BAND1, FakeClaude(BAND1, sentences={"吃": many}))
    assert kept(tmp_path, "吃") == ["我吃饭。", "爸爸吃饭。"]


# English translation check


@pytest.mark.parametrize(
    "english",
    ["", "我吃饭", "x" * 121, "...", "Café"],
    ids=["empty", "chinese", "too-long", "no-letter", "non-ascii"],
)
def test_sentence_with_bad_english_is_dropped(tmp_path, english):
    fake = FakeClaude(BAND1, sentences={"吃": [s("我吃饭。", english)]})
    result = run(tmp_path, BAND1, fake, retries=0)
    assert list(result.failed) == ["吃"]
    assert "吃" not in saved_ids(tmp_path)


@pytest.mark.parametrize(
    "english",
    ["I eat at 2 o'clock, right?", "x" * 120, "A"],
    ids=["punctuation-digits", "120-chars", "one-letter"],
)
def test_sentence_with_good_english_is_kept(tmp_path, english):
    fake = FakeClaude(BAND1, sentences={"吃": [s("我吃饭。", english)]})
    result = run(tmp_path, BAND1, fake, retries=0)
    assert list(result.failed) == []
    assert saved_by_id(tmp_path)["吃"]["sentences"][0]["english"] == english


def test_bad_english_on_one_sentence_keeps_the_other(tmp_path):
    pairs = [s("我吃饭。", "我吃饭"), s("爸爸吃饭。", "Dad eats.")]
    run(tmp_path, BAND1, FakeClaude(BAND1, sentences={"吃": pairs}), retries=0)
    assert kept(tmp_path, "吃") == ["爸爸吃饭。"]


# Resume, never shrinks, dropped words


def test_second_run_skips_current_passing_lines(tmp_path):
    run(tmp_path, DECK, FakeClaude())
    again = FakeClaude()
    result = run(tmp_path, DECK, again)
    assert again.prompts == []
    assert result.written == 0
    assert result.skipped == len(DECK)
    assert saved_ids(tmp_path) == IDS


def test_saved_line_with_more_than_two_passing_sentences_is_still_done(tmp_path):
    """ADR 0011: the bank grows past 2 per word (up to its cap, 10); the writer must
    skip such a line, not replace or trim it, and not call Claude for it."""
    four = [
        s("我是医生。", "I am a doctor."),
        s("爸爸是医生。", "Dad is a doctor."),
        s("我们是医生。", "We are doctors."),
        s("我爸爸是医生。", "My dad is a doctor."),
    ]
    write_saved(tmp_path, *[saved_line(w, four if w == "是" else GOOD[w]) for w in IDS])
    before = saved(tmp_path)
    fake = FakeClaude()
    result = run(tmp_path, DECK, fake)
    assert fake.prompts == []
    assert result.skipped == len(DECK)
    assert result.written == 0
    assert saved(tmp_path) == before
    assert len(kept(tmp_path, "是")) == 4


def test_resume_asks_only_for_missing_words_and_keeps_order(tmp_path):
    write_saved(tmp_path, saved_line("吃", GOOD["吃"]), saved_line("是", GOOD["是"]))
    result = run(tmp_path, BAND1, FakeClaude(BAND1))
    assert [e["cards"] for e in log_entries(tmp_path)] == [5]
    assert result.written == 5
    assert result.skipped == 2
    assert saved_ids(tmp_path) == BAND1_IDS


def test_old_prompt_version_is_redone(tmp_path):
    others = [saved_line(w, GOOD[w]) for w in BAND1_IDS if w != "吃"]
    write_saved(
        tmp_path, saved_line("吃", [s("我吃饭。", "I eat.")], version="0"), *others
    )
    result = run(tmp_path, BAND1, FakeClaude(BAND1))
    assert result.written == 1
    assert result.skipped == 6
    row = saved_by_id(tmp_path)["吃"]
    assert str(row["prompt_version"]) == block.PROMPT_VERSION
    assert kept(tmp_path, "吃") == ["我吃饭。", "爸爸吃饭。"]


def test_saved_line_that_now_fails_the_checker_is_redone(tmp_path):
    others = [saved_line(w, GOOD[w]) for w in BAND1_IDS if w != "吃"]
    write_saved(tmp_path, saved_line("吃", [BAD]), *others)
    fake = FakeClaude(BAND1)
    result = run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 1
    assert result.skipped == 6
    assert kept(tmp_path, "吃") == ["我吃饭。", "爸爸吃饭。"]


def test_old_lines_stay_when_claude_errors_before_replacing_them(tmp_path, monkeypatch):
    write_saved(tmp_path, *[saved_line(w, GOOD[w]) for w in BAND1_IDS])
    before = (tmp_path / "sentences.jsonl").read_text(encoding="utf-8")
    monkeypatch.setattr(block, "PROMPT_VERSION", NEXT)
    run_allowing_stop(tmp_path, BAND1, FakeClaude(BAND1, script={0: claude_error()}))
    assert saved(tmp_path) == [json.loads(t) for t in before.splitlines()]


def test_old_line_stays_when_its_word_fails_all_retries(tmp_path, monkeypatch):
    write_saved(tmp_path, *[saved_line(w, GOOD[w]) for w in BAND1_IDS])
    old = block.PROMPT_VERSION
    monkeypatch.setattr(block, "PROMPT_VERSION", NEXT)
    result = run(tmp_path, BAND1, FakeClaude(BAND1, sentences={"吃": [BAD]}))
    assert list(result.failed) == ["吃"]
    assert saved_ids(tmp_path) == BAND1_IDS
    versions = {r["id"]: str(r["prompt_version"]) for r in saved(tmp_path)}
    assert versions["吃"] == old
    assert {v for w, v in versions.items() if w != "吃"} == {NEXT}


def test_version_bump_with_limit_keeps_old_lines_for_the_rest(tmp_path, monkeypatch):
    write_saved(tmp_path, *[saved_line(w, GOOD[w]) for w in BAND1_IDS])
    old = block.PROMPT_VERSION
    monkeypatch.setattr(block, "PROMPT_VERSION", NEXT)
    run(tmp_path, BAND1, FakeClaude(BAND1), limit=2)
    assert saved_ids(tmp_path) == BAND1_IDS
    versions = [str(r["prompt_version"]) for r in saved(tmp_path)]
    assert versions == [NEXT, NEXT, old, old, old, old, old]


def test_line_for_word_no_longer_in_cards_is_dropped_with_warning(
    tmp_path, capsys, caplog, recwarn
):
    write_saved(tmp_path, saved_line("gone", [s("我吃饭。", "I eat.")]))
    run(tmp_path, BAND1, FakeClaude(BAND1), limit=2)
    assert saved_ids(tmp_path) == BAND1_IDS[:2]
    captured = capsys.readouterr()
    warned = " ".join(str(w.message) for w in recwarn)
    assert "gone" in captured.out + captured.err + caplog.text + warned


# --limit and --dry-run


def test_limit_writes_only_the_first_n_words_needing_sentences(tmp_path):
    result = run(tmp_path, BAND1, FakeClaude(BAND1), limit=3)
    assert result.written == 3
    assert saved_ids(tmp_path) == BAND1_IDS[:3]


def test_limit_counts_only_words_still_needing_sentences(tmp_path):
    run(tmp_path, BAND1, FakeClaude(BAND1), limit=3)
    run(tmp_path, BAND1, FakeClaude(BAND1), limit=3)
    assert saved_ids(tmp_path) == BAND1_IDS[:6]


def test_limit_zero_calls_nothing(tmp_path):
    fake = FakeClaude(BAND1)
    result = run(tmp_path, BAND1, fake, limit=0)
    assert fake.prompts == []
    assert result.written == 0


def test_dry_run_never_calls_claude_and_writes_nothing(tmp_path, capsys):
    fake = FakeClaude()
    run(tmp_path, DECK, fake, dry_run=True)
    assert fake.prompts == []
    assert list(tmp_path.iterdir()) == []
    assert "爸爸" in capsys.readouterr().out  # shows the first prompt


def test_dry_run_leaves_existing_file_unchanged(tmp_path):
    write_saved(tmp_path, saved_line("吃", [BAD]), saved_line("gone", GOOD["吃"]))
    before = (tmp_path / "sentences.jsonl").read_bytes()
    fake = FakeClaude()
    run(tmp_path, DECK, fake, dry_run=True)
    assert fake.prompts == []
    assert (tmp_path / "sentences.jsonl").read_bytes() == before


# Failure modes


def test_claude_unavailable_raises_and_writes_nothing(tmp_path):
    fake = FakeClaude(BAND1, script={0: claude_error("run `claude` and log in")})
    run_allowing_stop(tmp_path, BAND1, fake, chunk_size=2)
    assert len(fake.prompts) == 1
    assert saved(tmp_path) == []


def test_claude_error_keeps_work_so_far_and_makes_no_more_calls(tmp_path):
    fake = FakeClaude(BAND1, script={1: claude_error()})
    run_allowing_stop(tmp_path, BAND1, fake, chunk_size=2)
    assert len(fake.prompts) == 2
    assert saved_ids(tmp_path) == BAND1_IDS[:2]


def test_claude_error_during_a_retry_keeps_work_so_far(tmp_path):
    fake = FakeClaude(BAND1, sentences={"吃": [BAD]}, script={1: claude_error()})
    run_allowing_stop(tmp_path, BAND1, fake)
    assert saved_ids(tmp_path) == [w for w in BAND1_IDS if w != "吃"]


def test_rerun_after_claude_error_continues(tmp_path):
    stopped = FakeClaude(BAND1, script={1: claude_error()})
    run_allowing_stop(tmp_path, BAND1, stopped, chunk_size=2)
    result = run(tmp_path, BAND1, FakeClaude(BAND1), chunk_size=2)
    assert result.skipped == 2
    assert result.written == 5
    assert saved_ids(tmp_path) == BAND1_IDS


@pytest.mark.parametrize(
    "bad_text",
    [
        "Sure! Here are your sentences.",
        json.dumps({"sentences": ["我吃饭。"]}, ensure_ascii=False),
        json.dumps({"cards": "none"}),
    ],
    ids=["not-json", "wrong-shape", "cards-not-a-list"],
)
def test_broken_reply_fails_that_calls_words_and_run_goes_on(tmp_path, bad_text):
    fake = FakeClaude(BAND1, script={0: bad_text})
    result = run(tmp_path, BAND1, fake, chunk_size=4, retries=0)
    assert len(fake.prompts) == 2
    assert sorted(result.failed) == sorted(BAND1_IDS[:4])
    assert result.written == 3
    assert saved_ids(tmp_path) == BAND1_IDS[4:]


def test_reply_in_a_json_code_fence_is_fine(tmp_path):
    body = json.dumps(
        {"cards": [{"id": "吃", "sentences": items([s("我吃饭。", "I eat.")])}]},
        ensure_ascii=False,
    )
    write_saved(tmp_path, *[saved_line(w, GOOD[w]) for w in BAND1_IDS if w != "吃"])
    fake = FakeClaude(BAND1, script={0: "```json\n" + body + "\n```"})
    result = run(tmp_path, BAND1, fake)
    assert result.written == 1
    assert kept(tmp_path, "吃") == ["我吃饭。"]


def test_word_missing_from_reply_is_retried(tmp_path):
    fake = FakeClaude(BAND1, script={0: {"吃": None}})
    result = run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 2
    assert result.written == 7
    assert list(result.failed) == []
    assert saved_ids(tmp_path) == BAND1_IDS


def test_word_missing_from_reply_with_no_retries_is_failed(tmp_path):
    fake = FakeClaude(BAND1, sentences={"吃": None})
    result = run(tmp_path, BAND1, fake, retries=0)
    assert list(result.failed) == ["吃"]
    assert "吃" not in saved_ids(tmp_path)


def test_word_without_sentences_key_fails_alone(tmp_path):
    reply_cards = [
        {"id": w, "sentences": items(GOOD[w])} for w in BAND1_IDS if w != "吃"
    ] + [{"id": "吃"}]
    body = json.dumps({"cards": reply_cards}, ensure_ascii=False)
    result = run(tmp_path, BAND1, FakeClaude(BAND1, script={0: body}), retries=0)
    assert list(result.failed) == ["吃"]
    assert saved_ids(tmp_path) == [w for w in BAND1_IDS if w != "吃"]


def test_extra_word_in_reply_is_ignored(tmp_path):
    fake = FakeClaude(BAND1, sentences={"zz": GOOD["吃"]}, extra=["zz"])
    result = run(tmp_path, BAND1, fake)
    assert saved_ids(tmp_path) == BAND1_IDS
    assert list(result.failed) == []


def test_unreadable_saved_line_stops_before_any_call(tmp_path):
    broken = saved_line("爸爸", GOOD["爸爸"]) + "\n" + '{"id": "吃"' + "\n"
    (tmp_path / "sentences.jsonl").write_text(broken, encoding="utf-8")
    fake = FakeClaude(BAND1)
    with pytest.raises(Exception, match="line 2"):
        run(tmp_path, BAND1, fake)
    assert fake.prompts == []
    assert (tmp_path / "sentences.jsonl").read_text(encoding="utf-8") == broken


@pytest.mark.parametrize(
    "setting",
    [{"limit": -1}, {"chunk_size": 0}, {"retries": -1}],
    ids=["limit", "chunk_size", "retries"],
)
def test_bad_settings_raise_value_error(tmp_path, setting):
    fake = FakeClaude(BAND1)
    with pytest.raises(ValueError):
        run(tmp_path, BAND1, fake, **setting)
    assert fake.prompts == []


# pinyin_problems and layout_pinyin (Claude writes the pinyin, a script checks it;
# ADR 0010, SPEC "Pinyin")


def problems(hanzi, pinyin, words, cards=DECK) -> list[str]:
    return block.pinyin_problems(hanzi, pinyin, tuple(words), cards)


def test_right_pinyin_has_no_problems():
    assert (
        problems(
            "我爸爸是医生。",
            "wǒ bà ba shì yī shēng",
            words_of("我爸爸是医生。", "爸爸"),
        )
        == []
    )


@pytest.mark.parametrize(
    "pinyin", ["wǒ chī", "wǒ chī fàn le"], ids=["too-few", "too-many"]
)
def test_syllable_count_must_match_chinese_characters(pinyin):
    found = problems("我吃饭。", pinyin, ("我", "吃", "饭"))
    assert found
    said = " ".join(found)
    assert str(len(pinyin.split())) in said and "3" in said


def test_punctuation_in_claudes_pinyin_is_ignored():
    """Only runs of letters are syllables: commas, stops and spaces don't count."""
    hanzi = "我吃饭，爸爸吃饭！"
    words = words_of(hanzi, "吃")
    assert problems(hanzi, "wǒ chī fàn, bà ba chī fàn!", words) == []


def test_hsk_word_dictionary_reading_passes():
    """一起 is yī qǐ in our dictionary: the dictionary tone, no tone change."""
    words = ("我们", "一起", "吃", "饭")
    assert problems("我们一起吃饭。", "wǒ men yī qǐ chī fàn", words) == []


def test_hsk_word_with_a_tone_change_fails():
    """The prompt asks for the dictionary tone of 一 / 不; our dictionary says yī qǐ."""
    words = ("我们", "一起", "吃", "饭")
    found = problems("我们一起吃饭。", "wǒ men yì qǐ chī fàn", words)
    assert found
    assert any("一起" in p for p in found)


@pytest.mark.parametrize("reading", ["biàn yí", "pián yi"])
def test_either_reading_of_a_several_reading_word_passes(reading):
    deck = [*DECK, CHEAP]
    assert problems("饭便宜。", f"fàn {reading}", ("饭", "便宜"), deck) == []


def test_made_up_reading_of_an_hsk_word_fails_naming_the_word():
    deck = [*DECK, CHEAP]
    found = problems("饭便宜。", "fàn bian ya", ("饭", "便宜"), deck)
    assert found
    assert any("便宜" in p and "bian ya" in p for p in found)


def test_made_up_syllable_for_a_one_character_hsk_word_fails():
    found = problems("我吃饭。", "wǒ chā fàn", ("我", "吃", "饭"))
    assert found
    assert any("吃" in p for p in found)


def test_neutral_tone_as_the_dictionary_writes_it_is_fine():
    assert problems("爸爸吃饭。", "bà ba chī fàn", ("爸爸", "吃", "饭")) == []


@pytest.mark.parametrize(
    "pinyin",
    ["ba ba chī fàn", "bà ba chī fan", "ba ba chi fan"],
    ids=["first-syllable", "one-character-word", "all"],
)
def test_dropping_a_tone_mark_elsewhere_fails(pinyin):
    """Block-review round 1: toneless pinyin must not pass (learners need the tones)."""
    assert problems("爸爸吃饭。", pinyin, ("爸爸", "吃", "饭"))


@pytest.mark.parametrize(
    "sentence, pinyin, words, extra",
    [
        ("我是医生。", "wǒ shì yī sheng", ("我", "是", "医生"), []),
        ("我吃个饭。", "wǒ chī ge fàn", ("我", "吃", "个", "饭"), ["个"]),
    ],
    ids=["later-syllable", "ge"],
)
def test_neutral_tone_the_dictionary_does_not_write_fails(
    sentence, pinyin, words, extra
):
    """/code-review: any looser rule let wrong pinyin pass (老师 lǎo shi, 他来了
    tā lai le). The dictionary already writes the real neutral tones."""
    ge = card("个", "gě / gè", 1, ["measure word"], readings="2")
    deck = [*DECK, *([ge] if extra else [])]
    assert block.pinyin_problems(sentence, pinyin, words, deck)


def test_a_tone_where_the_dictionary_has_neutral_is_fine():
    """对不起 is duì bu qǐ in the dictionary; duì bù qǐ (the full tone) is fine."""
    sorry = card("对不起", "duì bu qǐ", 1, ["sorry"])
    found = block.pinyin_problems("对不起。", "duì bù qǐ", ("对不起",), [*DECK, sorry])
    assert found == []


@pytest.mark.parametrize("pinyin", ["wo3 chi1 fan4", "wǒ chī fàn4"])
def test_tone_numbers_fail(pinyin):
    found = problems("我吃饭。", pinyin, ("我", "吃", "饭"))
    assert any("tone numbers" in p for p in found)


def test_erhua_written_as_its_own_r_passes():
    nar = card("哪儿", "nǎ r", 1, ["where"])
    found = block.pinyin_problems(
        "我去哪儿？", "wǒ qù nǎ r", ("我", "去", "哪儿"), [*DECK, nar]
    )
    assert found == []


def test_erhua_glued_on_gets_a_hint():
    nar = card("哪儿", "nǎ r", 1, ["where"])
    found = block.pinyin_problems(
        "我去哪儿？", "wǒ qù nǎr", ("我", "去", "哪儿"), [*DECK, nar]
    )
    assert any("nǎ r" in p for p in found), found


def test_character_pypinyin_does_not_know_fails_with_none_known(monkeypatch):
    monkeypatch.setattr(block, "_char_readings", lambda ch: [])
    found = problems("我喝水。", "wǒ hē shuǐ", ("我", "喝", "水"))
    assert any("none known" in p for p in found), found


def test_check_falls_back_to_each_character_when_words_do_not_cover():
    """With no reading at all, each character is checked against pypinyin."""
    assert problems("我吃饭。", "wǒ chī fàn", ()) == []
    assert problems("我吃饭。", "wǒ chī huǒ", ())


def test_capitals_are_fine():
    assert problems("我吃饭。", "Wǒ CHĪ Fàn", ("我", "吃", "饭")) == []


@pytest.mark.parametrize(
    "hanzi, pinyin", [("女", "nv\u030c"), ("绿", "lv\u0300")], ids=["nü", "lü"]
)
def test_v_is_read_as_u_umlaut(hanzi, pinyin):
    """女 nǚ / 绿 lǜ (not in the toy deck: pypinyin's readings), v for ü, tone marked."""
    assert problems(hanzi, pinyin, (hanzi,)) == []


@pytest.mark.parametrize("pinyin", ["wǒ hē shuǐ", "wǒ hè shuǐ"])
def test_non_hsk_character_passes_any_pypinyin_reading(pinyin):
    """喝 and 水 aren't in the toy deck; pypinyin says 喝 is hē or hè."""
    assert problems("我喝水。", pinyin, ("我", "喝", "水")) == []


def test_non_hsk_character_with_a_wrong_reading_fails_naming_it():
    found = problems("我喝水。", "wǒ hē huǒ", ("我", "喝", "水"))
    assert found
    assert any("水" in p and "huǒ" in p for p in found)


def test_layout_spec_example():
    assert (
        block.layout_pinyin("我吃饭，爸爸吃饭！", "wǒ chī fàn bà ba chī fàn")
        == "wǒ chī fàn，bà ba chī fàn！"
    )


@pytest.mark.parametrize(
    "pinyin",
    [
        "wǒ bà ba shì yī shēng",
        "wǒ  bà ba shì yī shēng .",
        " wǒ bà ba, shì yī shēng。",
    ],
    ids=["plain", "extra-spaces-and-stop", "claudes-own-punctuation"],
)
def test_layout_uses_the_sentences_punctuation_with_no_space_around_it(pinyin):
    assert block.layout_pinyin("我爸爸是医生。", pinyin) == "wǒ bà ba shì yī shēng。"


# Writer-level pinyin (SPEC "Failure modes": a sentence failing the pinyin check)


@pytest.mark.parametrize(
    "bad_pinyin", ["wǒ chī", "wǒ chā fàn"], ids=["count", "made-up"]
)
def test_sentence_with_bad_pinyin_is_dropped_and_retried_with_the_reason(
    tmp_path, bad_pinyin
):
    bad = ("我吃饭。", bad_pinyin, "I eat.")
    fake = FakeClaude(BAND1, sentences={"吃": [bad]}, script={1: {"吃": GOOD["吃"]}})
    result = run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 2
    reasons = problems("我吃饭。", bad_pinyin, words_of("我吃饭。", "吃"), BAND1)
    assert reasons
    for reason in reasons:
        assert reason in fake.prompts[1]
    assert list(result.failed) == []
    assert kept(tmp_path, "吃") == ["我吃饭。", "爸爸吃饭。"]


def test_bad_pinyin_on_one_sentence_keeps_the_other(tmp_path):
    triples = [("我吃饭。", "wǒ chī", "I eat."), GOOD["吃"][1]]
    run(tmp_path, BAND1, FakeClaude(BAND1, sentences={"吃": triples}), retries=0)
    assert kept(tmp_path, "吃") == ["爸爸吃饭。"]


def test_sentence_without_pinyin_is_dropped(tmp_path):
    body = json.dumps(
        {
            "cards": [
                {"id": "吃", "sentences": [{"hanzi": "我吃饭。", "english": "I eat."}]}
            ]
        },
        ensure_ascii=False,
    )
    write_saved(tmp_path, *[saved_line(w, GOOD[w]) for w in BAND1_IDS if w != "吃"])
    result = run(tmp_path, BAND1, FakeClaude(BAND1, script={0: body}), retries=0)
    assert list(result.failed) == ["吃"]
    assert "吃" not in saved_ids(tmp_path)


def test_saved_pinyin_is_claudes_syllables_laid_out(tmp_path):
    """Claude's reading is kept (biàn yí here), laid out by layout_pinyin."""
    deck = [*DECK, CHEAP]
    claude_text = "fàn  biàn yí ."
    fake = FakeClaude(
        deck, sentences={"便宜": [("饭便宜。", claude_text, "Food is cheap.")]}
    )
    run(tmp_path, deck, fake, retries=0)
    pinyin = saved_by_id(tmp_path)["便宜"]["sentences"][0]["pinyin"]
    assert pinyin == block.layout_pinyin("饭便宜。", claude_text)
    assert pinyin == "fàn biàn yí。"


def test_saved_pinyin_keeps_mid_sentence_punctuation(tmp_path):
    hanzi = "我吃饭，爸爸吃饭！"
    triple = (hanzi, "wǒ chī fàn, bà ba chī fàn!", "I eat, dad eats!")
    run(tmp_path, BAND1, FakeClaude(BAND1, sentences={"吃": [triple]}), retries=0)
    pinyin = saved_by_id(tmp_path)["吃"]["sentences"][0]["pinyin"]
    assert pinyin == "wǒ chī fàn，bà ba chī fàn！"


@pytest.mark.parametrize("saved_pinyin", ["x", "wǒ chā fàn"], ids=["junk", "made-up"])
def test_saved_line_whose_pinyin_fails_the_check_is_redone(tmp_path, saved_pinyin):
    others = [saved_line(w, GOOD[w]) for w in BAND1_IDS if w != "吃"]
    write_saved(
        tmp_path, saved_line("吃", [("我吃饭。", saved_pinyin, "I eat.")]), *others
    )
    fake = FakeClaude(BAND1)
    result = run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 1
    assert result.skipped == 6
    assert result.written == 1
    assert saved_by_id(tmp_path)["吃"]["sentences"][0]["pinyin"] == "wǒ chī fàn。"


def test_reply_schema_asks_for_pinyin(tmp_path):
    seen = {}

    def ask(prompt, **kwargs):
        seen.update(kwargs)
        return FakeClaude(BAND1)(prompt)

    run(tmp_path, BAND1, ask, limit=1)
    assert "pinyin" in json.dumps(seen["json_schema"])


# Real file


@pytest.mark.skipif(not SENTENCES_JSONL.exists(), reason="sentences.jsonl not made yet")
def test_real_sentences_file_lines_all_pass_the_checker(real_cards):
    vocab = Vocab(real_cards)
    ids = {c.id for c in real_cards}
    text = SENTENCES_JSONL.read_text(encoding="utf-8")
    for row in (json.loads(t) for t in text.splitlines() if t.strip()):
        assert row["id"] in ids
        assert 1 <= len(row["sentences"]) <= 10  # the bank's cap (ADR 0011)
        for one in row["sentences"]:
            check = check_sentence(one["hanzi"], row["hanzi"], vocab)
            assert check.passed, one
            problems = block.pinyin_problems(
                one["hanzi"], one["pinyin"], check.words, real_cards
            )
            assert problems == [], (one, problems)
            assert one["pinyin"] == block.layout_pinyin(one["hanzi"], one["pinyin"])


# -- Settled while building (SPEC "Failure modes", the 7 test-writer assumptions) ----


def test_unreadable_saved_line_raises_sentence_file_error(tmp_path):
    (tmp_path / "sentences.jsonl").write_text('{"id": "吃"\n', encoding="utf-8")
    with pytest.raises(block.SentenceFileError, match="line 1"):
        run(tmp_path, BAND1, FakeClaude(BAND1))


def test_words_from_a_broken_reply_are_retried(tmp_path):
    fake = FakeClaude(BAND1, script={0: "not json"})
    result = run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 2
    assert [e["retry"] for e in log_entries(tmp_path)] == [0, 1]
    assert result.written == 7
    assert "no usable sentences came back" in fake.prompts[1]


def test_empty_deck_is_refused(tmp_path):
    with pytest.raises(ValueError):
        run(tmp_path, [], FakeClaude())


def test_ask_gets_model_system_and_schema(tmp_path):
    seen = {}

    def ask(prompt, **kwargs):
        seen.update(kwargs)
        return FakeClaude(BAND1)(prompt)

    run(tmp_path, BAND1, ask, limit=1)
    assert seen["model"] == "sonnet"
    assert seen["json_schema"]["required"] == ["cards"]
    assert seen["system"]


def test_command_line_prints_stopped_on_claude_error(monkeypatch, capsys):
    from hsk_trainer.blocks.sentence_writer import __main__ as cli

    def boom(*args, **kwargs):
        raise claude_error("usage limit reached")

    monkeypatch.setattr(cli, "write_sentences", boom)
    monkeypatch.setattr(cli, "load_cards", lambda path: DECK)
    assert cli.main(["--limit", "1"]) == 1
    out = capsys.readouterr().out
    assert "Stopped:" in out and "usage limit reached" in out


def test_command_line_prints_stopped_on_a_bad_setting(monkeypatch, capsys):
    from hsk_trainer.blocks.sentence_writer import __main__ as cli

    monkeypatch.setattr(cli, "load_cards", lambda path: DECK)
    assert cli.main(["--retries", "-1"]) == 1
    assert "Stopped:" in capsys.readouterr().out


# -- block-reviewer round 1 ------------------------------------------------------------


def test_word_listed_twice_keeps_the_first_passing_copy(tmp_path, capsys):
    others = [saved_line(w, GOOD[w]) for w in BAND1_IDS if w != "吃"]
    write_saved(
        tmp_path,
        saved_line("吃", [BAD]),
        saved_line("吃", [s("我吃饭。", "I eat.")]),
        saved_line("吃", [s("爸爸吃饭。", "Dad eats.")]),
        *others,
    )
    fake = FakeClaude(BAND1)
    result = run(tmp_path, BAND1, fake)
    assert fake.prompts == []  # a passing copy is enough: no call
    assert result.skipped == 7
    assert saved_ids(tmp_path) == BAND1_IDS  # one copy each, in cards order
    assert kept(tmp_path, "吃") == ["我吃饭。"]
    assert "listed twice" in capsys.readouterr().out


def test_same_sentence_twice_is_kept_once(tmp_path):
    twice = [
        s("我吃饭。", "I eat."),
        s("我吃饭。", "I eat."),
        s("爸爸吃饭。", "Dad eats."),
    ]
    run(tmp_path, BAND1, FakeClaude(BAND1, sentences={"吃": twice}))
    assert kept(tmp_path, "吃") == ["我吃饭。", "爸爸吃饭。"]


def test_command_line_prints_stopped_when_cards_file_is_missing(monkeypatch, capsys):
    from hsk_trainer.blocks.sentence_writer import __main__ as cli

    def missing(path):
        raise FileNotFoundError(path)

    monkeypatch.setattr(cli, "load_cards", missing)
    assert cli.main([]) == 1
    assert "Stopped:" in capsys.readouterr().out


def test_saved_line_with_the_same_sentence_twice_is_redone(tmp_path):
    same = [s("我吃饭。", "I eat."), s("我吃饭。", "I eat.")]
    others = [saved_line(w, GOOD[w]) for w in BAND1_IDS if w != "吃"]
    write_saved(tmp_path, saved_line("吃", same), *others)
    fake = FakeClaude(BAND1)
    run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 1
    assert kept(tmp_path, "吃") == ["我吃饭。", "爸爸吃饭。"]


# -- /code-review round 1 --------------------------------------------------------------


def test_curly_quotes_and_dashes_in_english_are_made_plain(tmp_path):
    fake = FakeClaude(
        BAND1, sentences={"吃": [s("我吃饭。", "I\u2019m eating \u2014 now.")]}
    )
    run(tmp_path, BAND1, fake, retries=0)
    assert saved_by_id(tmp_path)["吃"]["sentences"][0]["english"] == "I'm eating - now."


def test_slash_percent_and_ampersand_are_fine_in_english(tmp_path):
    fake = FakeClaude(
        BAND1, sentences={"吃": [s("我吃饭。", "He/she eats 100% & more.")]}
    )
    result = run(tmp_path, BAND1, fake, retries=0)
    assert list(result.failed) == []


def test_failed_words_reach_the_summary_after_a_claude_error(tmp_path, capsys):
    fake = FakeClaude(BAND1, sentences={"吃": [BAD]}, script={1: claude_error()})
    run_allowing_stop(tmp_path, BAND1, fake)
    assert "Failed (re-run to retry): 吃" in capsys.readouterr().out


def test_word_listed_twice_prefers_a_current_copy_over_an_older_one(tmp_path):
    others = [saved_line(w, GOOD[w]) for w in BAND1_IDS if w != "吃"]
    write_saved(
        tmp_path,
        saved_line("吃", [s("我吃饭。", "I eat.")], version="0"),
        saved_line("吃", [s("爸爸吃饭。", "Dad eats.")]),
        *others,
    )
    fake = FakeClaude(BAND1)
    run(tmp_path, BAND1, fake)
    assert fake.prompts == []
    assert kept(tmp_path, "吃") == ["爸爸吃饭。"]


def test_first_entry_wins_when_reply_repeats_a_word(tmp_path):
    good = items(GOOD["吃"])
    body = json.dumps(
        {"cards": [{"id": "吃", "sentences": good}, {"id": "吃", "sentences": []}]},
        ensure_ascii=False,
    )
    others = [saved_line(w, GOOD[w]) for w in BAND1_IDS if w != "吃"]
    write_saved(tmp_path, *others)
    fake = FakeClaude(BAND1, script={0: body})
    result = run(tmp_path, BAND1, fake)
    assert len(fake.prompts) == 1
    assert result.written == 1


def test_a_stray_item_in_the_reply_fails_alone(tmp_path):
    good = items(GOOD["吃"])
    body = json.dumps(
        {"cards": ["oops", {"id": "吃", "sentences": good}]}, ensure_ascii=False
    )
    others = [saved_line(w, GOOD[w]) for w in BAND1_IDS if w != "吃"]
    write_saved(tmp_path, *others)
    result = run(tmp_path, BAND1, FakeClaude(BAND1, script={0: body}))
    assert result.written == 1


# -- block-review round 2 --------------------------------------------------------------


def test_count_reason_shows_claudes_pinyin():
    found = problems("我吃饭。", "wǒchī fàn", ("我", "吃", "饭"))
    assert any("wǒchī fàn" in p for p in found), found


def test_retry_prompt_shows_the_rejected_pinyin(tmp_path):
    wrong = ("我吃饭。", "wǒ chā fàn", "I eat.")
    fake = FakeClaude(BAND1, sentences={"吃": [wrong]}, script={1: {"吃": GOOD["吃"]}})
    run(tmp_path, BAND1, fake)
    assert "wǒ chā fàn" in fake.prompts[1]


def test_same_sentence_with_corrected_pinyin_is_still_tried(tmp_path):
    wrong = ("我吃饭。", "wǒ chā fàn", "I eat.")
    right = ("我吃饭。", "wǒ chī fàn", "I eat.")
    fake = FakeClaude(BAND1, sentences={"吃": [wrong, right]})
    result = run(tmp_path, BAND1, fake, retries=0)
    assert list(result.failed) == []
    assert kept(tmp_path, "吃") == ["我吃饭。"]


def test_layout_turns_v_with_a_tone_mark_into_u_umlaut():
    assert block.layout_pinyin("绿。", "lv\u0300") == "lǜ。"


# -- block-review round 3 --------------------------------------------------------------


def test_full_tone_on_a_neutral_syllable_must_be_a_real_reading():
    """了 is le; lè is no reading of 了, so it fails (bù for 不 in 对不起 passes)."""
    le = card("了", "le", 1, ["particle"])
    found = block.pinyin_problems(
        "我吃饭了。", "wǒ chī fàn lè", ("我", "吃", "饭", "了"), [*DECK, le]
    )
    assert any("了" in p for p in found), found


# ---- write_one: one word, during the quiz (ADR 0011, used by live_sentences) -------


def one(tmp_path, word, ask, cards=DECK, **kwargs):
    """write_one for the card `word`, logging to tmp_path/log.jsonl."""
    target = next(c for c in cards if c.id == word)
    return block.write_one(target, cards, ask=ask, log=tmp_path / "log.jsonl", **kwargs)


def hanzi_list(result) -> list[str]:
    return [x.hanzi for x in result.sentences]


def test_write_one_defaults_match_spec():
    from quizkit.claude import ask_claude

    params = inspect.signature(block.write_one).parameters
    assert params["vocab"].default is None
    assert params["ask"].default is ask_claude
    assert params["timeout"].default == 30  # /code-review: near the 15 s wait
    assert params["log"].default == block.LIVE_LOG_FILE  # gitignored (block review)


def test_write_one_returns_passing_sentences_laid_out_with_the_model(tmp_path):
    result = one(tmp_path, "爸爸", FakeClaude())
    assert isinstance(result, block.WrittenSentences)
    assert result.model == FAKE_MODEL
    assert hanzi_list(result) == ["我爸爸是医生。", "爸爸吃饭。"]
    assert all(isinstance(x, block.Sentence) for x in result.sentences)
    assert result.sentences[0].pinyin == "wǒ bà ba shì yī shēng。"
    assert result.sentences[0].english == "My dad is a doctor."


def test_write_one_makes_exactly_one_call(tmp_path):
    fake = FakeClaude()
    one(tmp_path, "吃", fake)
    assert len(fake.prompts) == 1


def test_write_one_does_not_retry_when_nothing_passes(tmp_path):
    fake = FakeClaude(sentences={"吃": [BAD]})
    result = one(tmp_path, "吃", fake)
    assert result.sentences == []
    assert len(fake.prompts) == 1


def test_write_one_drops_failing_sentences(tmp_path):
    fake = FakeClaude(sentences={"吃": [BAD, s("我吃饭。", "I eat.")]})
    assert hanzi_list(one(tmp_path, "吃", fake)) == ["我吃饭。"]


def test_write_one_drops_bad_pinyin_and_bad_english(tmp_path):
    wrong_pinyin = ("我吃饭。", "wǒ chí fàn", "I eat.")
    bad_english = s("爸爸吃饭。", "爸爸吃饭")
    fake = FakeClaude(sentences={"吃": [wrong_pinyin, bad_english]})
    assert one(tmp_path, "吃", fake).sentences == []


def test_write_one_keeps_at_most_two(tmp_path):
    many = [
        s("我吃饭。", "I eat."),
        s("爸爸吃饭。", "Dad eats."),
        s("我们吃饭。", "We eat."),
    ]
    fake = FakeClaude(sentences={"吃": many})
    assert hanzi_list(one(tmp_path, "吃", fake)) == ["我吃饭。", "爸爸吃饭。"]


def test_write_one_drops_repeats(tmp_path):
    twice = [s("我吃饭。", "I eat."), s("我吃饭。", "I eat."), s("爸爸吃饭。", "D.")]
    fake = FakeClaude(sentences={"吃": twice})
    assert hanzi_list(one(tmp_path, "吃", fake)) == ["我吃饭。", "爸爸吃饭。"]


@pytest.mark.parametrize(
    "bad_text",
    [
        "Sure! Here are your sentences.",
        json.dumps({"sentences": ["我吃饭。"]}, ensure_ascii=False),
        json.dumps({"cards": "none"}),
    ],
    ids=["not-json", "wrong-shape", "cards-not-a-list"],
)
def test_write_one_broken_reply_gives_no_sentences(tmp_path, bad_text):
    result = one(tmp_path, "吃", FakeClaude(script={0: bad_text}))
    assert result.sentences == []


def test_write_one_word_missing_from_reply_gives_no_sentences(tmp_path):
    result = one(tmp_path, "吃", FakeClaude(sentences={"吃": None}))
    assert result.sentences == []


def test_write_one_claude_error_goes_up(tmp_path):
    from quizkit.claude import ClaudeError

    with pytest.raises(ClaudeError):
        one(tmp_path, "吃", FakeClaude(script={0: claude_error()}))


def test_write_one_logs_one_line_with_one_card_and_no_retry(tmp_path):
    one(tmp_path, "吃", FakeClaude(sentences={"吃": [BAD]}))
    (entry,) = log_entries(tmp_path)
    assert entry["cards"] == 1
    assert entry["retry"] == 0
    assert entry["model"] == FAKE_MODEL
    assert entry["prompt_version"] == block.PROMPT_VERSION
    assert (entry["input_tokens"], entry["output_tokens"]) == (100, 50)


def test_write_one_writes_nothing_to_the_sentences_file(tmp_path, monkeypatch):
    before = SENTENCES_JSONL.read_bytes() if SENTENCES_JSONL.exists() else None
    monkeypatch.setattr(block, "SENTENCES_FILE", tmp_path / "sentences.jsonl")
    one(tmp_path, "吃", FakeClaude())
    assert not (tmp_path / "sentences.jsonl").exists()
    assert [p.name for p in tmp_path.iterdir()] == ["log.jsonl"]
    after = SENTENCES_JSONL.read_bytes() if SENTENCES_JSONL.exists() else None
    assert after == before


def test_write_one_passes_the_timeout_to_ask(tmp_path):
    seen = []

    def ask(prompt, **kwargs):
        seen.append(kwargs)
        return FakeClaude()(prompt)

    one(tmp_path, "吃", ask)
    one(tmp_path, "吃", ask, timeout=5)
    assert [k.get("timeout") for k in seen] == [30, 5]
    assert seen[0]["model"] == "sonnet"


def test_write_one_prompt_uses_the_words_band_only(tmp_path):
    fake = FakeClaude()
    one(tmp_path, "吃", fake)
    (prompt,) = fake.prompts
    for word in BAND1_IDS:
        assert word in prompt
    assert "一起" not in prompt


def test_write_one_accepts_a_ready_vocab(tmp_path):
    result = one(tmp_path, "吃", FakeClaude(), vocab=Vocab(DECK))
    assert hanzi_list(result) == ["我吃饭。", "爸爸吃饭。"]


# -- block-review round 1 --------------------------------------------------------------


def test_write_one_log_defaults_to_the_gitignored_live_log():
    import inspect

    default = inspect.signature(block.write_one).parameters["log"].default
    assert default == block.LIVE_LOG_FILE
    assert default != block.LOG_FILE
    ignored = (block.ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/live_sentence_log.jsonl" in ignored


def test_write_one_skips_a_log_it_cannot_write(tmp_path):
    """A log path that can't be opened (here a folder) doesn't lose the sentences."""
    target = next(c for c in DECK if c.id == "爸爸")
    folder = tmp_path / "log.jsonl"
    folder.mkdir()
    result = block.write_one(target, DECK, ask=FakeClaude(), log=folder)
    assert hanzi_list(result) == ["我爸爸是医生。", "爸爸吃饭。"]


# ---- The removed list (ADR 0015): audited-out sentences never come back ------------
# SPEC: `removed` input, read_removed, "The removed list", "Picks up where it left
# off", and the three removed-list Failure-mode rows. Every run passes a tmp_path list.

AUDIT_REASON = "an audit removed this sentence"


def removed_at(tmp_path, data=None) -> Path:
    """A removed list in tmp_path (word -> removed sentences); None = no file."""
    path = tmp_path / "removed.json"
    if data is not None:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_removed_list_names_match_spec():
    assert block.REMOVED_FILE.name == "sentences_removed.json"
    assert block.REMOVED_FILE.parent.name == "generated"
    assert issubclass(block.RemovedListError, block.SentenceFileError)
    default = inspect.signature(block.write_sentences).parameters["removed"].default
    assert default == block.REMOVED_FILE


def test_sentence_bank_shares_the_writers_removed_list_names():
    """SPEC: sentence_bank imports REMOVED_FILE and RemovedListError from here."""
    import hsk_trainer.blocks.sentence_bank as bank

    assert bank.REMOVED_FILE is block.REMOVED_FILE
    assert bank.RemovedListError is block.RemovedListError


def test_read_removed_missing_file_is_empty(tmp_path):
    assert block.read_removed(tmp_path / "nope.json") == {}


def test_read_removed_reads_word_to_sentences(tmp_path):
    data = {"吃": ["我吃饭。"], "爸爸": ["爸爸吃饭。", "我爸爸是医生。"]}
    assert block.read_removed(removed_at(tmp_path, data)) == data


@pytest.mark.parametrize(
    "text",
    ["{not json", '["我吃饭。"]', '{"吃": "我吃饭。"}', '{"吃": [1]}'],
    ids=["broken-json", "not-an-object", "not-a-list", "not-text"],
)
def test_read_removed_bad_list_raises_naming_the_file(tmp_path, text):
    path = tmp_path / "removed.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(block.RemovedListError, match="removed.json"):
        block.read_removed(path)


def test_missing_removed_list_changes_nothing(tmp_path):
    result = run(tmp_path, BAND1, FakeClaude(BAND1), removed=removed_at(tmp_path))
    assert result.written == 7
    assert kept(tmp_path, "吃") == ["我吃饭。", "爸爸吃饭。"]


def test_removed_sentence_in_a_reply_is_not_saved_for_that_word(tmp_path):
    """Removed for 吃 only: 饭 may still use the same sentence."""
    removed = removed_at(tmp_path, {"吃": ["我吃饭。"]})
    fake = FakeClaude(BAND1)
    run(tmp_path, BAND1, fake, removed=removed)
    assert len(fake.prompts) == 1  # 吃 still has 爸爸吃饭。, so no retry
    assert kept(tmp_path, "吃") == ["爸爸吃饭。"]
    assert "我吃饭。" in kept(tmp_path, "饭")


def test_word_with_only_removed_sentences_is_retried_with_the_audit_reason(tmp_path):
    removed = removed_at(tmp_path, {"吃": ["我吃饭。", "爸爸吃饭。"]})
    new = [s("我们吃饭。", "We eat.")]
    fake = FakeClaude(BAND1, script={1: {"吃": new}})
    result = run(tmp_path, BAND1, fake, removed=removed)
    assert len(fake.prompts) == 2
    assert AUDIT_REASON in fake.prompts[1]
    assert list(result.failed) == []
    assert kept(tmp_path, "吃") == ["我们吃饭。"]


def test_removed_sentence_still_sent_after_retries_leaves_the_word_failed(tmp_path):
    removed = removed_at(tmp_path, {"吃": ["我吃饭。", "爸爸吃饭。"]})
    result = run(tmp_path, BAND1, FakeClaude(BAND1), removed=removed)
    assert list(result.failed) == ["吃"]
    assert "吃" not in saved_ids(tmp_path)


def test_saved_line_loses_its_removed_sentence_and_is_still_skipped(tmp_path):
    write_saved(tmp_path, *[saved_line(w, GOOD[w]) for w in BAND1_IDS])
    removed = removed_at(tmp_path, {"爸爸": ["爸爸吃饭。"]})
    fake = FakeClaude(BAND1)
    result = run(tmp_path, BAND1, fake, removed=removed)
    assert fake.prompts == []
    assert result.skipped == 7
    assert kept(tmp_path, "爸爸") == ["我爸爸是医生。"]  # file rewritten
    assert kept(tmp_path, "吃") == ["我吃饭。", "爸爸吃饭。"]  # other words untouched
    assert saved_ids(tmp_path) == BAND1_IDS


def test_saved_line_of_only_removed_sentences_is_dropped_and_redone(tmp_path):
    write_saved(tmp_path, *[saved_line(w, GOOD[w]) for w in BAND1_IDS])
    removed = removed_at(tmp_path, {"吃": ["我吃饭。", "爸爸吃饭。"]})
    fake = FakeClaude(BAND1, sentences={"吃": [s("我们吃饭。", "We eat.")]})
    result = run(tmp_path, BAND1, fake, removed=removed)
    assert [e["cards"] for e in log_entries(tmp_path)] == [1]  # only 吃 is asked
    assert result.skipped == 6
    assert result.written == 1
    assert kept(tmp_path, "吃") == ["我们吃饭。"]


def test_saved_line_of_only_removed_sentences_is_gone_even_if_not_redone(tmp_path):
    """The line is dropped (the file shrinks) even when the redo fails."""
    write_saved(tmp_path, *[saved_line(w, GOOD[w]) for w in BAND1_IDS])
    removed = removed_at(tmp_path, {"吃": ["我吃饭。", "爸爸吃饭。"]})
    result = run(tmp_path, BAND1, FakeClaude(BAND1), removed=removed, retries=0)
    assert list(result.failed) == ["吃"]
    assert saved_ids(tmp_path) == [w for w in BAND1_IDS if w != "吃"]


def test_dry_run_reads_the_removed_list_but_writes_nothing(tmp_path):
    write_saved(tmp_path, *[saved_line(w, GOOD[w]) for w in BAND1_IDS])
    before = (tmp_path / "sentences.jsonl").read_bytes()
    removed = removed_at(tmp_path, {"吃": ["我吃饭。", "爸爸吃饭。"]})
    fake = FakeClaude(BAND1)
    run(tmp_path, BAND1, fake, removed=removed, dry_run=True)
    assert fake.prompts == []
    assert (tmp_path / "sentences.jsonl").read_bytes() == before
    assert not (tmp_path / "log.jsonl").exists()
    (removed).write_text("{not json", encoding="utf-8")  # proof it's read in a dry run
    with pytest.raises(block.RemovedListError):
        run(tmp_path, BAND1, fake, removed=removed, dry_run=True)


def test_broken_removed_list_stops_before_any_call_and_changes_nothing(tmp_path):
    write_saved(tmp_path, saved_line("gone", GOOD["吃"]), saved_line("吃", [BAD]))
    before = (tmp_path / "sentences.jsonl").read_bytes()
    removed = tmp_path / "removed.json"
    removed.write_text('{"吃": "我吃饭。"}', encoding="utf-8")
    fake = FakeClaude(BAND1)
    with pytest.raises(block.RemovedListError, match="removed.json"):
        run(tmp_path, BAND1, fake, removed=removed)
    assert fake.prompts == []
    assert (tmp_path / "sentences.jsonl").read_bytes() == before
    assert not (tmp_path / "log.jsonl").exists()


def test_command_line_prints_stopped_on_a_broken_removed_list(monkeypatch, capsys):
    from hsk_trainer.blocks.sentence_writer import __main__ as cli

    def boom(*args, **kwargs):
        raise block.RemovedListError("sentences_removed.json: broken")

    monkeypatch.setattr(cli, "write_sentences", boom)
    monkeypatch.setattr(cli, "load_cards", lambda path: DECK)
    assert cli.main(["--limit", "1"]) == 1
    out = capsys.readouterr().out
    assert "Stopped:" in out and "sentences_removed.json" in out
