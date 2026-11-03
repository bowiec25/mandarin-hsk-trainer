"""Tests for the answer_writer block: contract (ID card + SPEC) and behaviour (from SPEC.md)."""

import json
from pathlib import Path

import pytest

import hsk_trainer.blocks.answer_writer as block
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.models import Card

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "answer_writer"
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
# The block's functions and quizkit.claude are reached through attributes / local
# imports (not at the top), so the contract tests above run before the block is built.

ANSWERS_JSONL = Path(__file__).parents[2] / "data" / "generated" / "answers.jsonl"
FAKE_MODEL = "fake-sonnet"


def make_cards(n: int) -> list[Card]:
    """n toy cards with ids w00, w01, ... (fixed width, so no id is inside another)."""
    return [
        Card(
            id=f"w{i:02d}",
            fields={"hanzi": f"字{i:02d}", "pinyin": f"zi{i}"},
            answers=[f"meaning {i}"],
            level=1 + i % 3,
        )
        for i in range(n)
    ]


def reply(text: str, input_tokens: int = 100, output_tokens: int = 50):
    from quizkit.claude import ClaudeReply

    return ClaudeReply(
        text=text,
        model=FAKE_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=0.01,
    )


def claude_error(msg: str = "usage limit reached"):
    from quizkit.claude import ClaudeError

    return ClaudeError(msg)


class FakeClaude:
    """Answers for every known card id found in the prompt; records each prompt.

    `answers` overrides what a card gets; `extra` adds ids Claude wasn't asked about;
    `drop` leaves ids out; `script` maps call number (0-based) to a raw reply text or
    an exception to raise.
    """

    def __init__(self, cards, answers=None, extra=(), drop=(), script=None):
        self.cards = cards
        self.answers = answers or {}
        self.extra = list(extra)
        self.drop = set(drop)
        self.script = script or {}
        self.prompts: list[str] = []

    def ids_in(self, prompt: str) -> list[str]:
        return [c.id for c in self.cards if c.id in prompt]

    def asked_ids(self) -> list[str]:
        return [i for p in self.prompts for i in self.ids_in(p)]

    def __call__(self, prompt: str):
        call = len(self.prompts)
        self.prompts.append(prompt)
        scripted = self.script.get(call)
        if isinstance(scripted, BaseException):
            raise scripted
        if isinstance(scripted, str):
            return reply(scripted)
        ids = [i for i in self.ids_in(prompt) if i not in self.drop] + self.extra
        body = {
            "cards": [
                {"id": i, "answers": self.answers.get(i, [f"answer {i[1:]}", "word"])}
                for i in ids
            ]
        }
        return reply(json.dumps(body))


def run(tmp_path, cards, ask, **kwargs):
    return block.write_answers(
        cards,
        ask=ask,
        out=tmp_path / "answers.jsonl",
        log=tmp_path / "log.jsonl",
        **kwargs,
    )


def run_allowing_stop(tmp_path, cards, ask, **kwargs):
    """Run until Claude fails: the SPEC says the ClaudeError goes up (work so far saved)."""
    from quizkit.claude import ClaudeError

    with pytest.raises(ClaudeError):
        run(tmp_path, cards, ask, **kwargs)


def saved(tmp_path) -> list[dict]:
    path = tmp_path / "answers.jsonl"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def saved_ids(tmp_path) -> list[str]:
    return [line["id"] for line in saved(tmp_path)]


# Output 1: answers.jsonl


def test_writes_one_line_per_card_with_spec_fields(tmp_path):
    cards = make_cards(3)
    run(tmp_path, cards, FakeClaude(cards))
    lines = saved(tmp_path)
    assert [line["id"] for line in lines] == ["w00", "w01", "w02"]
    first = lines[0]
    assert set(first) >= {"id", "hanzi", "answers", "model", "prompt_version"}
    assert first["hanzi"] == "字00"
    assert first["answers"] == ["answer 00", "word"]
    assert first["model"] == FAKE_MODEL
    assert str(first["prompt_version"]) == str(block.PROMPT_VERSION)


def test_saved_in_cards_order_even_if_reply_is_shuffled(tmp_path):
    cards = make_cards(4)
    order = ["w03", "w01", "w00", "w02"]
    shuffled = json.dumps({"cards": [{"id": i, "answers": ["word"]} for i in order]})
    run(tmp_path, cards, FakeClaude(cards, script={0: shuffled}))
    assert saved_ids(tmp_path) == ["w00", "w01", "w02", "w03"]


def test_saved_after_every_chunk(tmp_path):
    """If Claude stops on chunk 3, chunks 1 and 2 are already on disk."""
    cards = make_cards(6)
    fake = FakeClaude(cards, script={2: claude_error()})
    run_allowing_stop(tmp_path, cards, fake, chunk_size=2)
    assert saved_ids(tmp_path) == ["w00", "w01", "w02", "w03"]


def test_default_chunk_size_is_40(tmp_path):
    cards = make_cards(50)
    fake = FakeClaude(cards)
    run(tmp_path, cards, fake)
    assert [len(fake.ids_in(p)) for p in fake.prompts] == [40, 10]


def test_chunk_size_sets_cards_per_call(tmp_path):
    cards = make_cards(5)
    fake = FakeClaude(cards)
    run(tmp_path, cards, fake, chunk_size=2)
    assert [len(fake.ids_in(p)) for p in fake.prompts] == [2, 2, 1]


def test_prompt_shows_hanzi_pinyin_band_and_meanings(tmp_path):
    card = Card(
        id="吧", fields={"hanzi": "吧", "pinyin": "ba"}, answers=["particle"], level=2
    )
    fake = FakeClaude([card])
    run(tmp_path, [card], fake)
    prompt = fake.prompts[0]
    for bit in ["吧", "ba", "2", "particle"]:
        assert bit in prompt


# Output 2: the log


def test_log_has_one_line_per_claude_call(tmp_path):
    cards = make_cards(5)
    run(tmp_path, cards, FakeClaude(cards), chunk_size=2)
    text = (tmp_path / "log.jsonl").read_text(encoding="utf-8")
    entries = [json.loads(t) for t in text.splitlines() if t.strip()]
    assert len(entries) == 3
    for entry, n_cards in zip(entries, [2, 2, 1], strict=True):
        assert entry["model"] == FAKE_MODEL
        assert entry["prompt_version"] == block.PROMPT_VERSION
        assert entry["cards"] == n_cards
        assert (entry["input_tokens"], entry["output_tokens"]) == (100, 50)
        assert entry["cost_usd"] == pytest.approx(0.01)
        assert entry["time"]


def test_log_grows_across_runs(tmp_path):
    cards = make_cards(4)
    run(tmp_path, cards[:2], FakeClaude(cards))
    run(tmp_path, cards, FakeClaude(cards))
    text = (tmp_path / "log.jsonl").read_text(encoding="utf-8")
    assert len([t for t in text.splitlines() if t.strip()]) == 2


# Output 3: the summary


def test_summary_counts_written_and_tokens(tmp_path):
    cards = make_cards(5)
    result = run(tmp_path, cards, FakeClaude(cards), chunk_size=2)
    assert result.written == 5
    assert result.skipped == 0
    assert result.failed == []
    assert result.input_tokens == 300  # 3 calls x 100
    assert result.output_tokens == 150


def test_summary_printed_on_screen(tmp_path, capsys):
    cards = make_cards(2)
    run(tmp_path, cards, FakeClaude(cards))
    assert "2 written" in capsys.readouterr().out


# Resume and --limit


def test_second_run_skips_cards_already_done(tmp_path):
    cards = make_cards(4)
    run(tmp_path, cards, FakeClaude(cards))
    again = FakeClaude(cards)
    result = run(tmp_path, cards, again)
    assert again.prompts == []
    assert result.written == 0
    assert result.skipped == 4
    assert saved_ids(tmp_path) == ["w00", "w01", "w02", "w03"]


def test_resume_only_asks_for_missing_cards_and_keeps_order(tmp_path):
    cards = make_cards(4)
    run(tmp_path, [cards[1], cards[3]], FakeClaude(cards))
    again = FakeClaude(cards)
    result = run(tmp_path, cards, again)
    assert again.asked_ids() == ["w00", "w02"]
    assert result.written == 2
    assert result.skipped == 2
    assert saved_ids(tmp_path) == ["w00", "w01", "w02", "w03"]


def test_limit_20_writes_exactly_20(tmp_path):
    cards = make_cards(50)
    result = run(tmp_path, cards, FakeClaude(cards), limit=20)
    assert result.written == 20
    assert saved_ids(tmp_path) == [c.id for c in cards[:20]]


def test_limit_counts_only_cards_still_needing_answers(tmp_path):
    cards = make_cards(10)
    run(tmp_path, cards, FakeClaude(cards), limit=3)
    run(tmp_path, cards, FakeClaude(cards), limit=3)
    assert saved_ids(tmp_path) == [c.id for c in cards[:6]]


# --dry-run


def test_dry_run_never_calls_claude_and_writes_nothing(tmp_path, capsys):
    cards = make_cards(3)
    fake = FakeClaude(cards)
    run(tmp_path, cards, fake, dry_run=True)
    assert fake.prompts == []
    assert list(tmp_path.iterdir()) == []
    assert "w00" in capsys.readouterr().out  # shows what would be sent


# Failure modes


def test_claude_unavailable_stops_before_any_work(tmp_path):
    cards = make_cards(6)
    fake = FakeClaude(cards, script={0: claude_error("run `claude` and log in")})
    run_allowing_stop(tmp_path, cards, fake, chunk_size=2)
    assert len(fake.prompts) == 1
    assert saved(tmp_path) == []


def test_claude_error_stops_run_and_keeps_work_so_far(tmp_path):
    cards = make_cards(6)
    fake = FakeClaude(cards, script={1: claude_error()})
    run_allowing_stop(tmp_path, cards, fake, chunk_size=2)
    assert len(fake.prompts) == 2  # no third call after the error
    assert saved_ids(tmp_path) == ["w00", "w01"]


def test_rerun_after_claude_error_continues(tmp_path):
    cards = make_cards(6)
    stopped = FakeClaude(cards, script={1: claude_error()})
    run_allowing_stop(tmp_path, cards, stopped, chunk_size=2)
    again = FakeClaude(cards)
    run(tmp_path, cards, again, chunk_size=2)
    assert again.asked_ids() == ["w02", "w03", "w04", "w05"]
    assert saved_ids(tmp_path) == [c.id for c in cards]


@pytest.mark.parametrize(
    "bad_text",
    [
        "Sure! Here are the answers.",
        json.dumps({"answers": ["dad"]}),
        json.dumps({"cards": [{"id": "w00"}]}),
    ],
    ids=["not-json", "wrong-shape", "card-without-answers"],
)
def test_broken_reply_fails_chunk_and_run_goes_on(tmp_path, bad_text):
    cards = make_cards(4)
    fake = FakeClaude(cards, script={0: bad_text})
    result = run(tmp_path, cards, fake, chunk_size=2)
    assert len(fake.prompts) == 2
    assert sorted(result.failed) == ["w00", "w01"]
    assert result.written == 2
    assert saved_ids(tmp_path) == ["w02", "w03"]


def test_reply_in_a_json_code_fence_is_fine(tmp_path):
    cards = make_cards(2)
    body = json.dumps({"cards": [{"id": c.id, "answers": ["word"]} for c in cards]})
    fenced = "```json\n" + body + "\n```"
    result = run(tmp_path, cards, FakeClaude(cards, script={0: fenced}))
    assert result.written == 2
    assert saved_ids(tmp_path) == ["w00", "w01"]


def test_card_missing_from_reply_is_failed_and_retried(tmp_path):
    cards = make_cards(3)
    result = run(tmp_path, cards, FakeClaude(cards, drop={"w01"}))
    assert result.failed == ["w01"]
    assert saved_ids(tmp_path) == ["w00", "w02"]
    again = FakeClaude(cards)
    run(tmp_path, cards, again)
    assert again.asked_ids() == ["w01"]
    assert saved_ids(tmp_path) == ["w00", "w01", "w02"]


def test_extra_card_in_reply_is_ignored(tmp_path):
    cards = make_cards(2)
    result = run(tmp_path, cards, FakeClaude(cards, extra=["zz99"]))
    assert saved_ids(tmp_path) == ["w00", "w01"]
    assert result.written == 2
    assert result.failed == []


@pytest.mark.parametrize(
    "bad_answers",
    [[], ["爸爸"], ["x" * 41], ["father (coll.)"]],
    ids=["empty", "chinese", "too-long", "brackets"],
)
def test_card_failing_checker_is_not_saved_rest_of_chunk_is(tmp_path, bad_answers):
    cards = make_cards(3)
    result = run(tmp_path, cards, FakeClaude(cards, answers={"w01": bad_answers}))
    assert "w01" in result.failed
    assert saved_ids(tmp_path) == ["w00", "w02"]


def test_stale_card_in_answers_file_is_dropped_with_warning(
    tmp_path, capsys, caplog, recwarn
):
    cards = make_cards(2)
    stale = {
        "id": "gone",
        "hanzi": "没",
        "answers": ["old"],
        "model": FAKE_MODEL,
        "prompt_version": str(block.PROMPT_VERSION),
    }
    (tmp_path / "answers.jsonl").write_text(json.dumps(stale) + "\n", encoding="utf-8")
    run(tmp_path, cards, FakeClaude(cards))
    assert saved_ids(tmp_path) == ["w00", "w01"]
    captured = capsys.readouterr()
    warned = " ".join(str(w.message) for w in recwarn)
    assert "gone" in captured.out + captured.err + caplog.text + warned


# The checker: validate_answers


def line(card_id: str, answers: list[str]):
    """An AnswerLine built without validation, so the checker (not pydantic) judges it."""
    return block.AnswerLine.model_construct(
        id=card_id, hanzi="字", answers=answers, model=FAKE_MODEL, prompt_version="1"
    )


def test_checker_passes_good_answers():
    cards = make_cards(2)
    lines = [
        line("w00", ["father", "dad", "papa", "8", "p.m."]),  # digits are fine (八)
        line("w01", ["to look after", "o'clock", "well-known", "x" * 40]),
    ]
    assert block.validate_answers(lines, cards) == []


def test_checker_allows_ten_answers():
    ten = [f"word {c}" for c in "abcdefghij"]
    assert block.validate_answers([line("w00", ten)], make_cards(1)) == []


@pytest.mark.parametrize(
    "answers",
    [
        [],
        [f"word {c}" for c in "abcdefghijk"],
        [""],
        ["x" * 41],
        ["爸爸"],
        ["dad (coll.)"],
        ["dad!"],
        ["dad", "DAD"],
    ],
    ids=[
        "none",
        "eleven",
        "blank",
        "too-long",
        "chinese",
        "brackets",
        "punctuation",
        "dup",
    ],
)
def test_checker_catches_bad_answers(answers):
    problems = block.validate_answers([line("w00", answers)], make_cards(1))
    assert problems
    assert any("w00" in p for p in problems)


def test_checker_catches_unknown_card():
    problems = block.validate_answers([line("nope", ["dad"])], make_cards(1))
    assert any("nope" in p for p in problems)


def test_checker_catches_card_listed_twice():
    lines = [line("w00", ["dad"]), line("w00", ["father"])]
    problems = block.validate_answers(lines, make_cards(1))
    assert any("w00" in p for p in problems)


def test_checker_missing_card_only_matters_with_require_all():
    cards = make_cards(2)
    lines = [line("w00", ["dad"])]
    assert block.validate_answers(lines, cards) == []
    problems = block.validate_answers(lines, cards, require_all=True)
    assert any("w01" in p for p in problems)


# Real file


@pytest.mark.skipif(not ANSWERS_JSONL.exists(), reason="answers.jsonl not made yet")
def test_real_answers_file_covers_every_real_card(real_cards):
    text = ANSWERS_JSONL.read_text(encoding="utf-8")
    lines = [
        block.AnswerLine.model_validate_json(t) for t in text.splitlines() if t.strip()
    ]
    assert block.validate_answers(lines, real_cards, require_all=True) == []


# Extra cases from the block-reviewer


def test_broken_answers_file_stops_before_any_call(tmp_path):
    cards = make_cards(2)
    broken = '{"id": "w00"}' + "\n"
    (tmp_path / "answers.jsonl").write_text(broken, encoding="utf-8")
    fake = FakeClaude(cards)
    with pytest.raises(block.AnswerFileError, match="line 1"):
        run(tmp_path, cards, fake)
    assert fake.prompts == []
    assert (tmp_path / "answers.jsonl").read_text(encoding="utf-8") == broken


@pytest.mark.parametrize("bad", [["dad", None], "dad", None, 7])
def test_card_with_non_text_answers_fails_alone(tmp_path, bad):
    cards = make_cards(3)
    result = run(tmp_path, cards, FakeClaude(cards, answers={"w01": bad}))
    assert result.failed == ["w01"]
    assert saved_ids(tmp_path) == ["w00", "w02"]


@pytest.mark.parametrize("answers", [["-"], ["'"], [" - "]])
def test_checker_needs_a_letter_or_digit(answers):
    assert block.validate_answers([line("w00", answers)], make_cards(1))


def test_command_line_prints_stopped_and_exits_1(monkeypatch, capsys):
    from hsk_trainer.blocks.answer_writer import __main__ as cli

    def boom(*args, **kwargs):
        raise claude_error("usage limit reached")

    monkeypatch.setattr(cli, "write_answers", boom)
    monkeypatch.setattr(cli, "load_cards", lambda path: make_cards(1))
    assert cli.main(["--limit", "1"]) == 1
    out = capsys.readouterr().out
    assert "Stopped:" in out and "usage limit reached" in out


def test_negative_limit_is_refused(tmp_path):
    cards = make_cards(3)
    with pytest.raises(ValueError):
        run(tmp_path, cards, FakeClaude(cards), limit=-1)


@pytest.mark.parametrize(
    "error",
    [
        lambda: block.AnswerFileError("answers.jsonl line 3 can't be read"),
        lambda: ValueError("limit can't be negative"),
    ],
)
def test_command_line_reports_file_and_setting_errors(monkeypatch, capsys, error):
    from hsk_trainer.blocks.answer_writer import __main__ as cli

    def boom(*args, **kwargs):
        raise error()

    monkeypatch.setattr(cli, "write_answers", boom)
    monkeypatch.setattr(cli, "load_cards", lambda path: make_cards(1))
    assert cli.main([]) == 1
    assert "Stopped:" in capsys.readouterr().out


def test_repeats_in_claudes_reply_are_removed_not_failed(tmp_path):
    cards = make_cards(2)
    fake = FakeClaude(cards, answers={"w01": ["dad", "Dad", "father", " dad "]})
    result = run(tmp_path, cards, fake)
    assert result.failed == []
    assert saved(tmp_path)[1]["answers"] == ["dad", "father"]


@pytest.mark.parametrize("answers", [["."], ["..."]])
def test_checker_full_stops_alone_are_not_an_answer(answers):
    assert block.validate_answers([line("w00", answers)], make_cards(1))


# Extra cases from /code-review


def saved_line(card_id, answers, version=None):
    return json.dumps(
        {
            "id": card_id,
            "hanzi": "字",
            "answers": answers,
            "model": FAKE_MODEL,
            "prompt_version": version or str(block.PROMPT_VERSION),
        },
        ensure_ascii=False,
    )


def write_saved(tmp_path, *rows):
    text = "".join(r + "\n" for r in rows)
    (tmp_path / "answers.jsonl").write_text(text, encoding="utf-8")


def test_to_love_and_love_count_as_a_repeat():
    problems = block.validate_answers([line("w00", ["love", "To love"])], make_cards(1))
    assert any("twice" in p for p in problems)


def test_repeats_the_grader_sees_are_removed_from_reply(tmp_path):
    cards = make_cards(1)
    fake = FakeClaude(cards, answers={"w00": ["love", "to love", "Love!"]})
    run(tmp_path, cards, fake)
    assert saved(tmp_path)[0]["answers"] == ["love"]


def test_saved_repeats_are_tidied_without_calling_claude(tmp_path):
    cards = make_cards(1)
    write_saved(tmp_path, saved_line("w00", ["love", "to love"]))
    fake = FakeClaude(cards)
    run(tmp_path, cards, fake)
    assert fake.prompts == []
    assert saved(tmp_path)[0]["answers"] == ["love"]


def test_stale_line_is_removed_from_file_even_when_nothing_to_do(tmp_path):
    cards = make_cards(1)
    write_saved(tmp_path, saved_line("w00", ["dad"]), saved_line("gone", ["old"]))
    run(tmp_path, cards, FakeClaude(cards))
    assert saved_ids(tmp_path) == ["w00"]


@pytest.mark.parametrize(
    "rows",
    [
        [saved_line("w00", ["爸爸"])],
        [saved_line("w00", ["dad"], version="0")],
        [saved_line("w00", ["dad"]), saved_line("w00", ["father"])],
    ],
    ids=["fails-checker", "old-prompt-version", "listed-twice"],
)
def test_bad_or_old_saved_lines_are_asked_again(tmp_path, rows):
    cards = make_cards(1)
    write_saved(tmp_path, *rows)
    fake = FakeClaude(cards)
    run(tmp_path, cards, fake)
    assert fake.asked_ids() == ["w00"]
    assert saved(tmp_path)[0]["answers"] == ["answer 00", "word"]


def test_card_without_answers_key_fails_alone(tmp_path):
    cards = make_cards(3)
    reply_cards = [
        {"id": "w00", "answers": ["a"]},
        {"id": "w01"},
        {"id": "w02", "answers": ["b"]},
    ]
    body = json.dumps({"cards": reply_cards})
    result = run(tmp_path, cards, FakeClaude(cards, script={0: body}))
    assert result.failed == ["w01"]
    assert saved_ids(tmp_path) == ["w00", "w02"]


def test_summary_still_printed_when_claude_stops_the_run(tmp_path, capsys):
    cards = make_cards(4)
    fake = FakeClaude(cards, script={1: claude_error()})
    run_allowing_stop(tmp_path, cards, fake, chunk_size=2)
    assert "2 written" in capsys.readouterr().out


def test_non_text_answers_are_not_reported_as_repeats():
    problems = block.validate_answers([line("w00", [None, 5])], make_cards(1))
    assert not any("twice" in p for p in problems)


def test_line_saved_three_times_is_asked_again(tmp_path):
    cards = make_cards(1)
    write_saved(tmp_path, *[saved_line("w00", ["dad"])] * 3)
    fake = FakeClaude(cards)
    run(tmp_path, cards, fake)
    assert fake.asked_ids() == ["w00"]
    assert saved_ids(tmp_path) == ["w00"]


def test_dry_run_leaves_an_untidy_file_unchanged(tmp_path):
    cards = make_cards(1)
    write_saved(
        tmp_path, saved_line("w00", ["love", "to love"]), saved_line("gone", ["x"])
    )
    before = (tmp_path / "answers.jsonl").read_bytes()
    fake = FakeClaude(cards)
    run(tmp_path, cards, fake, dry_run=True)
    assert fake.prompts == []
    assert (tmp_path / "answers.jsonl").read_bytes() == before


# Contract: the reader is one of the Outputs (SPEC.md "The reader")


def test_block_spec_lists_load_answers_as_an_output():
    assert "load_answers(path, cards) -> dict[str, list[str]]" in (
        block.BLOCK_SPEC.outputs
    )


# Never shrinks the file: a line is only removed when its card is gone


def old_file(tmp_path, cards, version="1"):
    """Pre-write a line for every card, made by an older prompt."""
    write_saved(tmp_path, *[saved_line(c.id, ["old"], version=version) for c in cards])


def versions(tmp_path) -> dict[str, str]:
    return {row["id"]: str(row["prompt_version"]) for row in saved(tmp_path)}


def test_version_bump_with_limit_keeps_old_lines_for_the_rest(tmp_path, monkeypatch):
    cards = make_cards(4)
    old_file(tmp_path, cards)
    monkeypatch.setattr(block, "PROMPT_VERSION", "2")
    run(tmp_path, cards, FakeClaude(cards), limit=2)
    assert saved_ids(tmp_path) == ["w00", "w01", "w02", "w03"]
    assert versions(tmp_path) == {"w00": "2", "w01": "2", "w02": "1", "w03": "1"}


def test_version_bump_with_failed_chunk_keeps_old_lines(tmp_path, monkeypatch):
    cards = make_cards(4)
    old_file(tmp_path, cards)
    monkeypatch.setattr(block, "PROMPT_VERSION", "2")
    fake = FakeClaude(cards, script={0: "not json at all"})
    run(tmp_path, cards, fake, chunk_size=2)
    assert saved_ids(tmp_path) == ["w00", "w01", "w02", "w03"]
    assert versions(tmp_path) == {"w00": "1", "w01": "1", "w02": "2", "w03": "2"}
    assert saved(tmp_path)[0]["answers"] == ["old"]


def test_version_bump_with_claude_error_keeps_old_lines(tmp_path, monkeypatch):
    cards = make_cards(4)
    old_file(tmp_path, cards)
    monkeypatch.setattr(block, "PROMPT_VERSION", "2")
    fake = FakeClaude(cards, script={1: claude_error()})
    run_allowing_stop(tmp_path, cards, fake, chunk_size=2)
    assert saved_ids(tmp_path) == ["w00", "w01", "w02", "w03"]
    assert versions(tmp_path) == {"w00": "2", "w01": "2", "w02": "1", "w03": "1"}


def test_claude_error_on_first_call_after_bump_leaves_file_whole(tmp_path, monkeypatch):
    cards = make_cards(3)
    old_file(tmp_path, cards)
    monkeypatch.setattr(block, "PROMPT_VERSION", "2")
    run_allowing_stop(tmp_path, cards, FakeClaude(cards, script={0: claude_error()}))
    assert saved_ids(tmp_path) == ["w00", "w01", "w02"]
    assert set(versions(tmp_path).values()) == {"1"}


def test_version_bump_card_failing_checker_keeps_its_old_line(tmp_path, monkeypatch):
    cards = make_cards(3)
    old_file(tmp_path, cards)
    monkeypatch.setattr(block, "PROMPT_VERSION", "2")
    result = run(tmp_path, cards, FakeClaude(cards, answers={"w01": ["爸爸"]}))
    assert "w01" in result.failed
    assert saved_ids(tmp_path) == ["w00", "w01", "w02"]
    assert versions(tmp_path) == {"w00": "2", "w01": "1", "w02": "2"}


def test_saved_line_failing_checker_stays_until_replaced(tmp_path):
    cards = make_cards(1)
    write_saved(tmp_path, saved_line("w00", ["爸爸"]))
    run_allowing_stop(tmp_path, cards, FakeClaude(cards, script={0: claude_error()}))
    assert saved(tmp_path) == [json.loads(saved_line("w00", ["爸爸"]))]


def test_line_listed_twice_keeps_the_first_until_replaced(tmp_path):
    cards = make_cards(1)
    write_saved(tmp_path, saved_line("w00", ["dad"]), saved_line("w00", ["father"]))
    run_allowing_stop(tmp_path, cards, FakeClaude(cards, script={0: claude_error()}))
    assert saved_ids(tmp_path) == ["w00"]
    assert saved(tmp_path)[0]["answers"] == ["dad"]


def test_old_line_is_replaced_once_redone(tmp_path, monkeypatch):
    cards = make_cards(2)
    old_file(tmp_path, cards)
    monkeypatch.setattr(block, "PROMPT_VERSION", "2")
    run(tmp_path, cards, FakeClaude(cards))
    assert saved_ids(tmp_path) == ["w00", "w01"]
    assert set(versions(tmp_path).values()) == {"2"}


# The reader: load_answers(path, cards)


def answers_file(tmp_path, *rows) -> Path:
    write_saved(tmp_path, *rows)
    return tmp_path / "answers.jsonl"


def test_load_answers_gives_every_cards_answers_by_id(tmp_path):
    cards = make_cards(2)
    path = answers_file(
        tmp_path, saved_line("w00", ["dad", "father"]), saved_line("w01", ["mum"])
    )
    assert block.load_answers(path, cards) == {
        "w00": ["dad", "father"],
        "w01": ["mum"],
    }


def test_load_answers_ignores_lines_for_other_ids(tmp_path):
    cards = make_cards(1)
    path = answers_file(
        tmp_path,
        saved_line("other", ["爸爸"]),  # would fail the checker, but isn't ours
        saved_line("w00", ["dad"]),
        saved_line("w05", ["five"]),
    )
    assert block.load_answers(path, cards) == {"w00": ["dad"]}


def test_load_answers_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(block.AnswerFileError):
        block.load_answers(tmp_path / "nope.jsonl", make_cards(1))


def test_load_answers_directory_raises_answer_file_error_not_oserror(tmp_path):
    folder = tmp_path / "answers.jsonl"
    folder.mkdir()
    with pytest.raises(block.AnswerFileError):
        block.load_answers(folder, make_cards(1))


def test_load_answers_unreadable_line_names_its_line_number(tmp_path):
    cards = make_cards(2)
    path = answers_file(tmp_path, saved_line("w00", ["dad"]), '{"id": "w01"')
    with pytest.raises(block.AnswerFileError, match="line 2"):
        block.load_answers(path, cards)


def test_load_answers_card_with_no_line_raises(tmp_path):
    cards = make_cards(2)
    path = answers_file(tmp_path, saved_line("w00", ["dad"]))
    with pytest.raises(block.AnswerFileError, match="w01"):
        block.load_answers(path, cards)


def test_load_answers_line_listed_twice_raises(tmp_path):
    cards = make_cards(1)
    path = answers_file(tmp_path, saved_line("w00", ["dad"]), saved_line("w00", ["pa"]))
    with pytest.raises(block.AnswerFileError, match="w00"):
        block.load_answers(path, cards)


@pytest.mark.parametrize(
    "answers",
    [[], ["爸爸"], ["x" * 41], ["dad (coll.)"]],
    ids=["none", "chinese", "too-long", "brackets"],
)
def test_load_answers_line_failing_checker_raises(tmp_path, answers):
    cards = make_cards(1)
    path = answers_file(tmp_path, saved_line("w00", answers))
    with pytest.raises(block.AnswerFileError, match="w00"):
        block.load_answers(path, cards)


def test_load_answers_tidies_repeated_answers_like_the_writer(tmp_path):
    """SPEC: repeats ("love" / "To love") are tidied away, not an error."""
    cards = make_cards(1)
    path = answers_file(tmp_path, saved_line("w00", ["love", "To love", "like"]))
    assert block.load_answers(path, cards) == {"w00": ["love", "like"]}


def test_load_answers_lists_first_5_problems_then_how_many_more(tmp_path):
    cards = make_cards(9)
    path = answers_file(tmp_path, saved_line("w00", ["dad"]))  # 8 cards have no line
    with pytest.raises(block.AnswerFileError, match="and 3 more"):
        block.load_answers(path, cards)


@pytest.mark.skipif(not ANSWERS_JSONL.exists(), reason="answers.jsonl not made yet")
def test_load_answers_reads_real_file_for_all_real_cards(real_cards):
    answers = block.load_answers(ANSWERS_JSONL, real_cards)
    assert len(answers) == 978
    assert set(answers) == {c.id for c in real_cards}


# Follow-up from the block-reviewer


def test_load_answers_skips_blank_lines(tmp_path):
    cards = make_cards(2)
    path = tmp_path / "answers.jsonl"
    text = "\n" + saved_line("w00", ["dad"]) + "\n\n   \n" + saved_line("w01", ["mum"])
    path.write_text(text + "\n\n", encoding="utf-8")
    assert block.load_answers(path, cards) == {"w00": ["dad"], "w01": ["mum"]}


def test_writer_skips_blank_lines_and_keeps_every_line(tmp_path):
    cards = make_cards(2)
    path = tmp_path / "answers.jsonl"
    text = "\n" + saved_line("w00", ["dad"]) + "\n\n" + saved_line("w01", ["mum"])
    path.write_text(text + "\n\n", encoding="utf-8")
    fake = FakeClaude(cards)
    run(tmp_path, cards, fake)
    assert fake.prompts == []
    assert saved_ids(tmp_path) == ["w00", "w01"]


@pytest.mark.parametrize("how", ["claude-down", "limit-0"])
def test_listed_twice_bad_then_good_keeps_the_good_copy_once(tmp_path, how):
    cards = make_cards(1)
    write_saved(tmp_path, saved_line("w00", ["爸爸"]), saved_line("w00", ["dad"]))
    if how == "claude-down":
        fake = FakeClaude(cards, script={0: claude_error()})
        run_allowing_stop(tmp_path, cards, fake)
    else:
        run(tmp_path, cards, FakeClaude(cards), limit=0)
    assert saved_ids(tmp_path) == ["w00"]
    assert saved(tmp_path)[0]["answers"] == ["dad"]
    assert block.load_answers(tmp_path / "answers.jsonl", cards) == {"w00": ["dad"]}


def test_load_answers_non_utf8_file_raises_answer_file_error(tmp_path):
    path = tmp_path / "answers.jsonl"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(block.AnswerFileError):
        block.load_answers(path, make_cards(1))


def test_old_line_kept_for_redo_is_not_counted_as_skipped(tmp_path, monkeypatch):
    cards = make_cards(3)
    old_file(tmp_path, cards)
    monkeypatch.setattr(block, "PROMPT_VERSION", "2")
    result = run(tmp_path, cards, FakeClaude(cards), limit=1)
    assert result.written == 1
    assert result.skipped == 0
