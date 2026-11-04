"""Tests for the `hsk` command line (M3 Step 5).

CliRunner plays the quiz with scripted keystrokes: `input="love\\neight\\n"` types two
answers, each followed by Enter. Running out of input = end-of-input (quit).
"""

import functools
import os
import re
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from hsk_trainer.blocks.answer_writer import load_answers
from hsk_trainer.cli import ANSWERS_FILE, CARDS_FILE, app
from quizkit.files import load_cards

runner = CliRunner()


@pytest.fixture(autouse=True)
def own_judge_cache(tmp_path, monkeypatch):
    """Never read or write the developer's real data/judge_cache.jsonl."""
    monkeypatch.setattr("hsk_trainer.cli.JUDGE_CACHE", tmp_path / "judge_cache.jsonl")


@functools.cache
def _cards():
    return load_cards(CARDS_FILE)


def play(*args: str, typed: str = "") -> tuple[int, str]:
    result = runner.invoke(app, ["quiz", *args], input=typed)
    return result.exit_code, result.output


def deck_words(*args: str) -> list[str]:
    """The hanzi the quiz shows, in order, with no answers typed (it quits at once)."""
    from hsk_trainer.modes import HSK_MODES
    from quizkit.blocks.deck_builder import build_deck

    # Mirror of the CLI's deck, used to know which answers to type.
    opts = dict(zip(args[::2], args[1::2]))
    deck = build_deck(
        _cards(),
        HSK_MODES[opts.get("--mode", "char")],
        int(opts.get("--n", "10")),
        levels=[int(opts.get("--band", "1"))],
        seed=int(opts["--seed"]),
    )
    return [q.card_id for q in deck]


@functools.cache
def seed_for(word: str, band: str = "1") -> str:
    """A seed whose 1-word deck for `band` is `word` (searched once, then cached)."""
    return next(
        str(s)
        for s in range(5000)
        if deck_words("--band", band, "--n", "1", "--seed", str(s)) == [word]
    )


@functools.cache
def _answers() -> dict[str, list[str]]:
    return load_answers(ANSWERS_FILE, _cards())


def accepted(word: str) -> list[str]:
    """The answers the quiz accepts for `word`: its line in answers.jsonl (ADR 0006)."""
    return _answers()[word]


def right_answers(words: list[str]) -> list[str]:
    return [accepted(w)[0] for w in words]


# --- playing a whole quiz ---------------------------------------------------------


def test_all_right_scores_full_marks():
    args = ("--band", "1", "--n", "5", "--seed", "1")
    typed = "\n".join(right_answers(deck_words(*args))) + "\n"
    code, out = play(*args, typed=typed)
    assert code == 0
    assert out.count("✅") == 5
    assert "Score: 5/5" in out


def test_shows_the_hanzi_being_asked():
    args = ("--band", "1", "--n", "3", "--seed", "2")
    _, out = play(*args, typed="x\nx\nx\n")
    for word in deck_words(*args):
        assert word in out


def test_wrong_answer_shows_the_right_ones():
    args = ("--band", "1", "--n", "1", "--seed", "3")
    [word] = deck_words(*args)
    code, out = play(*args, typed="zzzzzzzz\n")
    assert code == 0
    assert "❌" in out
    assert accepted(word)[0] in out
    assert "Score: 0/1" in out


def test_love_and_to_love_both_count_for_ai():
    """Issue #16 "Done when": "love" and "to love" both count as correct for 爱."""
    for typed in ("love", "to love"):
        _, out = play("--n", "1", "--seed", seed_for("爱"), typed=typed + "\n")
        assert "✅" in out, typed
        assert "Score: 1/1" in out


def test_synonym_from_the_answer_list_counts():
    """M4 Step 4a checkpoint: "dad" for 爸爸 (only the answer list has it)."""
    _, out = play("--n", "1", "--seed", seed_for("爸爸"), typed="dad\n")
    assert "✅" in out
    assert "Score: 1/1" in out


def test_old_dictionary_sense_no_longer_counts():
    """ADR 0006: the old dictionary list accepted "modem" for 猫; the answer list doesn't."""
    _, out = play("--n", "1", "--seed", seed_for("猫"), typed="modem\n")
    assert "❌" in out
    assert "Score: 0/1" in out


def test_typo_is_forgiven_and_noted():
    _, out = play("--n", "1", "--seed", seed_for("爱"), typed="lvoe\n")
    assert "✅" in out
    assert "typo" in out.lower()


def test_typo_message_shows_the_answer_as_written():
    """Not the grader's normalised form: "haven't", never "havent"."""
    _, out = play("--n", "1", "--seed", seed_for("没有"), typed="havnt\n")
    assert "typo" in out.lower()
    assert "haven't" in out
    assert "havent" not in out


def test_wrong_answer_keeps_apostrophes():
    _, out = play("--n", "1", "--seed", seed_for("没有"), typed="zzzzzzzz\n")
    assert "don't have" in out
    assert "dont have" not in out


def test_char_pinyin_mode_shows_pinyin(real_cards):
    args = ("--band", "1", "--mode", "char_pinyin", "--n", "1", "--seed", "4")
    [word] = deck_words(*args)
    _, out = play(*args, typed="x\n")
    pinyin = {c.id: c for c in real_cards}[word].fields["pinyin"]
    assert pinyin in out


def test_char_mode_hides_pinyin(real_cards):
    args = ("--band", "1", "--mode", "char", "--n", "1", "--seed", "4")
    [word] = deck_words(*args)
    _, out = play(*args, typed="x\n")
    pinyin = {c.id: c for c in real_cards}[word].fields["pinyin"]
    assert pinyin not in out


def test_band_picks_only_that_bands_words(real_cards):
    band_of = {c.id: c.level for c in real_cards}
    for band in ("1", "2", "3"):
        words = deck_words("--band", band, "--n", "20", "--seed", "5")
        assert {band_of[w] for w in words} == {int(band)}


def test_same_seed_same_deck():
    args = ("--band", "3", "--n", "4", "--seed", "9")
    assert play(*args, typed="")[1] == play(*args, typed="")[1]


# --- quitting keeps the score so far (carry-over from Step 4) -----------------------


def test_end_of_input_quits_and_keeps_score():
    args = ("--band", "1", "--n", "5", "--seed", "6")
    first_two = right_answers(deck_words(*args)[:2])
    code, out = play(*args, typed="\n".join(first_two) + "\n")  # then input runs out
    assert code == 0
    assert "Stopped after 2 of 5" in out
    assert "Score: 2/2" in out


def test_quit_before_any_answer():
    code, out = play("--n", "3", "--seed", "1", typed="")
    assert code == 0
    assert "Stopped after 0 of 3" in out
    assert "Traceback" not in out


def test_ctrl_c_quits_and_keeps_score(monkeypatch):
    args = ("--band", "1", "--n", "3", "--seed", "7")
    first = right_answers(deck_words(*args)[:1])[0]
    answers = iter([first])

    def fake_input(prompt: str = "") -> str:
        try:
            return next(answers)
        except StopIteration:
            raise KeyboardInterrupt from None

    monkeypatch.setattr("builtins.input", fake_input)
    code, out = play(*args)
    assert code == 0
    assert "Stopped after 1 of 3" in out
    assert "Score: 1/1" in out


def test_ctrl_c_after_typing_still_keeps_score(monkeypatch):
    """Windows quirk: Ctrl-C can arrive just *after* input() returns, mid-feedback."""
    from hsk_trainer import cli

    args = ("--band", "1", "--n", "3", "--seed", "7")
    typed = "\n".join(right_answers(deck_words(*args))) + "\n"
    real_tell, calls = cli._tell, []

    def tell_then_interrupt(attempt):
        calls.append(attempt)
        real_tell(attempt)
        if len(calls) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_tell", tell_then_interrupt)
    code, out = play(*args, typed=typed)
    assert code == 0
    assert "Stopped after 2 of 3" in out
    assert "Score: 2/2" in out
    assert "Traceback" not in out


# --- short deck message ----------------------------------------------------------


def test_short_deck_says_how_many_words():
    code, out = play("--band", "2", "--n", "500", "--seed", "1", typed="")
    assert code == 0
    assert "Only 197 band-2 words" in out
    assert "of 197" in out


def test_no_short_deck_message_when_enough_words():
    _, out = play("--band", "2", "--n", "5", "--seed", "1", typed="")
    assert "Only" not in out


# --- friendly errors -------------------------------------------------------------


@pytest.mark.parametrize("band", ["0", "4", "-1"])
def test_bad_band_is_refused(band):
    code, out = play("--band", band)
    assert code != 0
    assert "Traceback" not in out


@pytest.mark.parametrize("n", ["0", "-3"])
def test_bad_n_is_refused(n):
    code, _ = play("--n", n)
    assert code != 0


def test_unknown_mode_is_refused():
    code, out = play("--mode", "banana")
    assert code != 0
    assert "char_pinyin" in out  # tells you what is allowed


def test_missing_cards_file_says_how_to_fix(tmp_path, monkeypatch):
    from hsk_trainer import cli

    monkeypatch.setattr(cli, "CARDS_FILE", tmp_path / "cards.jsonl")
    code, out = play()
    assert code == 1
    assert "normalizer" in out
    assert "Traceback" not in out


def test_custom_missing_file_gives_no_normalizer_hint(tmp_path):
    code, out = play("--cards", str(tmp_path / "nope.jsonl"))
    assert code == 1
    assert "nope.jsonl" in out


def test_broken_cards_file_is_a_friendly_error(tmp_path):
    broken = tmp_path / "cards.jsonl"
    broken.write_text(
        '{"id": "爱", "fields": {"hanzi": "爱"', encoding="utf-8"
    )  # cut off
    code, out = play("--cards", str(broken))
    assert code == 1
    assert "Can't build a quiz" in out
    assert "Traceback" not in out


def test_no_cards_in_that_band_is_a_friendly_error(tmp_path, real_cards):
    band1_only = tmp_path / "cards.jsonl"
    band1_only.write_text(
        "\n".join(c.model_dump_json() for c in real_cards if c.level == 1),
        encoding="utf-8",
    )
    code, out = play("--band", "3", "--cards", str(band1_only))
    assert code == 1
    assert "Can't build a quiz" in out


def test_missing_answers_file_says_how_to_fix(tmp_path, monkeypatch):
    from hsk_trainer import cli

    monkeypatch.setattr(cli, "ANSWERS_FILE", tmp_path / "answers.jsonl")
    code, out = play()
    assert code == 1
    assert "answers.jsonl" in out
    assert "git checkout" in out
    assert "answer_writer" in out
    assert "Traceback" not in out


def test_custom_missing_answers_file_gives_no_writer_hint(tmp_path):
    """The writer only makes the real file, so the hint would mislead for --answers."""
    code, out = play("--answers", str(tmp_path / "mine.jsonl"))
    assert code == 1
    assert "mine.jsonl" in out
    assert "answer_writer" not in out
    assert "Traceback" not in out


def test_bad_line_in_another_band_does_not_block_this_band(tmp_path):
    """A broken band-3 line only stops band-3 quizzes."""
    from hsk_trainer.blocks.answer_writer import AnswerLine

    lines = ANSWERS_FILE.read_text(encoding="utf-8").splitlines()
    band3 = {c.id for c in _cards() if c.level == 3}
    first3 = next(
        i
        for i, raw in enumerate(lines)
        if AnswerLine.model_validate_json(raw).id in band3
    )
    bad = AnswerLine.model_validate_json(lines[first3]).model_copy(
        update={"answers": ["爸爸"]}
    )
    lines[first3] = bad.model_dump_json()
    path = tmp_path / "answers.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert play("--band", "1", "--answers", str(path), typed="")[0] == 0
    code, out = play("--band", "3", "--answers", str(path), typed="")
    assert code == 1
    assert "Can't build a quiz" in out


def test_answers_file_missing_a_card_is_a_friendly_error(tmp_path):
    lines = ANSWERS_FILE.read_text(encoding="utf-8").splitlines()
    short = tmp_path / "answers.jsonl"
    short.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")  # first card gone
    code, out = play("--answers", str(short))
    assert code == 1
    assert "Can't build a quiz" in out
    assert "missing" in out
    assert "Traceback" not in out


def test_answers_path_that_is_a_folder_is_a_friendly_error(tmp_path):
    code, out = play("--answers", str(tmp_path))  # exists, but can't be read
    assert code == 1
    assert "Can't build a quiz" in out
    assert "Traceback" not in out


def test_broken_answers_line_is_a_friendly_error(tmp_path):
    broken = tmp_path / "answers.jsonl"
    broken.write_text('{"id": "爱", "answers": ["love"\n', encoding="utf-8")  # cut off
    code, out = play("--answers", str(broken))
    assert code == 1
    assert "Can't build a quiz" in out
    assert "line 1" in out
    assert "Traceback" not in out


def test_help_lists_the_options():
    result = runner.invoke(app, ["quiz", "--help"])
    assert result.exit_code == 0
    # On GitHub Actions, rich colours the help, splitting "--band" with colour codes.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    for opt in ("--band", "--mode", "--n", "--seed", "--no-judge"):
        assert opt in plain


# --- the Claude judge (M4 Step 4b, ADR 0007) -----------------------------------
# A fake ClaudeJudge stands in; the real one is tested in tests/blocks/test_judge.py.


def fake_judge_class(monkeypatch, correct: bool, reason: str = "Judged."):
    """Swap the CLI's ClaudeJudge for a fake; returns what it was asked."""
    from quizkit.blocks.judge import Verdict

    asked: list[str] = []

    class FakeJudge:
        def __init__(self, subject, cache_file=None, before_asking=None, **kw):
            assert subject and cache_file is not None
            self.before_asking = before_asking

        def __call__(self, question, typed):
            if self.before_asking:
                self.before_asking()
            asked.append(typed)
            return Verdict(correct=correct, reason=reason, source="claude")

    monkeypatch.setattr("hsk_trainer.cli.ClaudeJudge", FakeJudge)
    return asked


def test_judge_yes_counts_and_says_why(monkeypatch):
    asked = fake_judge_class(monkeypatch, True, "Old man is slang for father.")
    _, out = play("--n", "1", "--seed", seed_for("爸爸"), typed="old man\n")
    assert asked == ["old man"]
    assert "asking the judge" in out
    assert "✅ accepted by the Claude judge: Old man is slang for father." in out
    assert "Score: 1/1" in out


def test_judge_no_stays_wrong_and_says_why(monkeypatch):
    fake_judge_class(monkeypatch, False, "Mother is a different word.")
    _, out = play("--n", "1", "--seed", seed_for("爸爸"), typed="mother\n")
    assert "❌" in out
    assert "judge: Mother is a different word." in out
    assert "Score: 0/1" in out


def test_judge_not_asked_when_the_list_says_right(monkeypatch):
    asked = fake_judge_class(monkeypatch, False)
    _, out = play("--n", "1", "--seed", seed_for("爸爸"), typed="dad\n")
    assert asked == []
    assert "asking the judge" not in out


def test_no_judge_never_asks(monkeypatch):
    asked = fake_judge_class(monkeypatch, True)
    _, out = play(
        "--n", "1", "--seed", seed_for("爸爸"), "--no-judge", typed="old man\n"
    )
    assert asked == []
    assert "Score: 0/1" in out


def test_judge_unreachable_keeps_the_quiz_going():
    """No fake: the real ClaudeJudge, with `claude` "not installed" (conftest)."""
    _, out = play("--n", "1", "--seed", seed_for("爸爸"), typed="old man\n")
    assert "❌" in out
    assert "(judge couldn't check:" in out
    assert "Score: 0/1" in out


# --- the real program, through a pipe -------------------------------------------


def test_hanzi_print_through_a_pipe_on_any_os():
    """Windows pipes default to a non-UTF-8 code page; printing 爱 must not crash."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("PYTHONIOENCODING", "PYTHONUTF8")
    }
    proc = subprocess.run(
        [sys.executable, "-c", "from hsk_trainer.cli import main; main()", "quiz"]
        + ["--mode", "char_pinyin", "--n", "2", "--seed", "1", "--no-judge"],
        check=False,  # we check returncode ourselves, to show stderr on failure
        input=b"x\nx\n",
        capture_output=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    out = proc.stdout.decode("utf-8")
    assert "Score: 0/2" in out


# --- the sentence modes (M4 Step 5, ADR 0011: banked sentences) -------------------
# Hidden --sentences / --seen point the quiz at a tmp bank and seen file; --no-judge
# and --no-live (ADR 0011: bank only) keep Claude out. A 1-word deck's word depends
# only on the seed, not the mode.

SENTENCE = ("我爸爸是医生。", "wǒ bà ba shì yī shēng。", "My dad is a doctor.")


def bank_file(tmp_path, word="爸爸", sentence=SENTENCE):
    import json

    hanzi, pinyin, english = sentence
    path = tmp_path / "sentences.jsonl"
    row = {
        "id": word,
        "hanzi": word,
        "sentences": [{"hanzi": hanzi, "pinyin": pinyin, "english": english}],
        "model": "fake-sonnet",
        "prompt_version": "2",
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def play_sentences(tmp_path, mode, sentences, typed, word="爸爸", live=False):
    return play(
        "--mode", mode, "--n", "1", "--seed", seed_for(word), "--no-judge",
        "--sentences", str(sentences), "--seen", str(tmp_path / "seen.json"),
        *([] if live else ["--no-live"]),
        typed=typed,
    )  # fmt: skip


@pytest.mark.parametrize("mode", ["char_sentence", "full"])
def test_sentence_modes_play(tmp_path, mode):
    code, out = play_sentences(
        tmp_path, mode, bank_file(tmp_path), accepted("爸爸")[0] + "\n"
    )
    assert code == 0, out
    assert "Score: 1/1" in out
    assert "Traceback" not in out


@pytest.mark.parametrize("mode", ["char_sentence", "full"])
def test_banked_sentence_is_shown_under_the_word(tmp_path, mode):
    _, out = play_sentences(tmp_path, mode, bank_file(tmp_path), "x\n")
    lines = out.splitlines()
    at = next(i for i, text in enumerate(lines) if SENTENCE[0] in text)
    assert any("爸爸" in text and SENTENCE[0] not in text for text in lines[:at])


def test_full_mode_shows_the_sentence_pinyin(tmp_path):
    _, out = play_sentences(tmp_path, "full", bank_file(tmp_path), "x\n")
    assert SENTENCE[1].rstrip("。") in out


def test_char_sentence_mode_hides_the_sentence_pinyin(tmp_path):
    _, out = play_sentences(tmp_path, "char_sentence", bank_file(tmp_path), "x\n")
    assert SENTENCE[1].rstrip("。") not in out
    assert "bà ba" not in out  # nor the word's pinyin


@pytest.mark.parametrize("mode", ["char_sentence", "full"])
@pytest.mark.parametrize("typed", ["right", "zzzzzzzz"])
def test_sentence_english_is_shown_only_after_the_answer(tmp_path, mode, typed):
    answer = accepted("爸爸")[0] if typed == "right" else typed
    _, out = play_sentences(tmp_path, mode, bank_file(tmp_path), answer + "\n")
    mark = "✅" if typed == "right" else "❌"
    assert SENTENCE[2] in out
    assert out.index(SENTENCE[0]) < out.index(mark) < out.index(SENTENCE[2])


def test_english_not_shown_when_quitting_before_answering(tmp_path):
    _, out = play_sentences(tmp_path, "char_sentence", bank_file(tmp_path), "")
    assert SENTENCE[0] in out
    assert SENTENCE[2] not in out


@pytest.mark.parametrize("mode", ["char_sentence", "full"])
def test_word_without_a_sentence_says_so_and_still_plays(tmp_path, mode):
    other = bank_file(
        tmp_path, word="猫", sentence=("猫吃饭。", "māo chī fàn。", "A cat eats.")
    )
    code, out = play_sentences(tmp_path, mode, other, accepted("爸爸")[0] + "\n")
    assert code == 0, out
    assert "no example sentence" in out.lower()
    assert "猫吃饭。" not in out
    assert "Score: 1/1" in out


def test_missing_bank_file_says_no_sentence_and_still_plays(tmp_path):
    code, out = play_sentences(
        tmp_path, "full", tmp_path / "none.jsonl", accepted("爸爸")[0] + "\n"
    )
    assert code == 0, out
    assert "no example sentence" in out.lower()
    assert "Score: 1/1" in out


@pytest.mark.parametrize("mode", ["char_sentence", "full"])
def test_seen_file_is_written(tmp_path, mode):
    import json

    play_sentences(tmp_path, mode, bank_file(tmp_path), "x\n")
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert SENTENCE[0] in seen["爸爸"]


def test_char_modes_never_write_the_seen_file(tmp_path):
    play_sentences(tmp_path, "char", bank_file(tmp_path), "x\n")
    assert not (tmp_path / "seen.json").exists()


def test_broken_bank_file_gives_a_clean_error(tmp_path):
    bad = tmp_path / "sentences.jsonl"
    bad.write_text('{"id": "爸爸"\n', encoding="utf-8")
    code, out = play_sentences(tmp_path, "full", bad, "x\n")
    assert code != 0
    assert "sentence bank" in out
    assert "Traceback" not in out


def test_seen_file_that_cannot_be_saved_does_not_stop_the_quiz(tmp_path, monkeypatch):
    from hsk_trainer.blocks import sentence_bank

    def locked(*args, **kwargs):
        raise PermissionError("locked")

    monkeypatch.setattr(sentence_bank, "write_atomically", locked)
    code, out = play_sentences(
        tmp_path, "full", bank_file(tmp_path), accepted("爸爸")[0] + "\n"
    )
    assert code == 0, out
    assert "Score: 1/1" in out
    assert "couldn't save" in out


# --- live sentences in the sentence modes (M4 Step 5, ADR 0011, live_sentences) -----
# A fake writer stands in for sentence_writer.write_one (as used by the
# live_sentences block's default writer); the real one would only raise ClaudeError here (conftest).

LIVE = ("爸爸是医生。", "bà ba shì yī shēng。", "Dad is a doctor.")


class FakeWriteOne:
    """Records which cards it was asked about; answers with one sentence at once."""

    def __init__(self, triple=LIVE):
        self.triple = triple
        self.calls: list[str] = []
        self.asked = {}  # card id -> threading.Event, set once asked

    def event(self, word):
        import threading

        return self.asked.setdefault(word, threading.Event())

    def __call__(self, card, *args, **kwargs):
        from hsk_trainer.blocks import sentence_writer

        self.calls.append(card.id)
        self.event(card.id).set()
        hanzi, pinyin, english = self.triple
        one = sentence_writer.Sentence(hanzi=hanzi, pinyin=pinyin, english=english)
        return sentence_writer.WrittenSentences(sentences=[one], model="fake-sonnet")


@pytest.fixture
def fake_writer(monkeypatch):
    fake = FakeWriteOne()
    # The live block's default writer calls write_one from its own module.
    monkeypatch.setattr("hsk_trainer.blocks.live_sentences.write_one", fake)
    return fake


def test_help_lists_no_live():
    result = runner.invoke(app, ["quiz", "--help"])
    assert "--no-live" in re.sub(r"\x1b\[[0-9;]*m", "", result.output)


@pytest.mark.parametrize("mode", ["char_sentence", "full"])
def test_no_live_never_calls_the_writer(tmp_path, mode, fake_writer):
    code, out = play_sentences(
        tmp_path, mode, tmp_path / "none.jsonl", accepted("爸爸")[0] + "\n"
    )
    assert code == 0, out
    assert fake_writer.calls == []
    assert "no example sentence" in out.lower()


@pytest.mark.parametrize("mode", ["char_sentence", "full"])
def test_live_sentence_is_shown_and_banked(tmp_path, mode, fake_writer):
    import json

    bank = tmp_path / "sentences.jsonl"  # missing: an empty bank, so the rule says new
    code, out = play_sentences(tmp_path, mode, bank, "x\n", live=True)
    assert code == 0, out
    assert "Traceback" not in out
    assert fake_writer.calls[0] == "爸爸"
    assert LIVE[0] in out
    assert LIVE[2] in out  # its English after the answer
    rows = [json.loads(t) for t in bank.read_text(encoding="utf-8").splitlines() if t]
    saved = {r["id"]: [s["hanzi"] for s in r["sentences"]] for r in rows}
    assert saved["爸爸"] == [LIVE[0]]
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert LIVE[0] in seen["爸爸"]


def test_live_writer_unreachable_falls_back_to_the_bank(tmp_path):
    """The real writer: conftest makes `claude` look missing, so the bank is used."""
    code, out = play_sentences(
        tmp_path, "full", bank_file(tmp_path), accepted("爸爸")[0] + "\n", live=True
    )
    assert code == 0, out
    assert "Traceback" not in out
    assert "Score: 1/1" in out


def test_next_sentence_is_prepared_while_you_answer(tmp_path, monkeypatch, fake_writer):
    """When the first answer is read, the second word's sentence is already asked for."""
    from hsk_trainer import cli

    seed = "1"
    first, second = deck_words("--n", "2", "--seed", seed)
    asked_at_first_read = []
    real_read = cli._read

    def read():
        if not asked_at_first_read:
            asked_at_first_read.append(fake_writer.event(second).wait(2))
        return real_read()

    monkeypatch.setattr(cli, "_read", read)
    code, out = play(
        "--mode", "char_sentence", "--n", "2", "--seed", seed, "--no-judge",
        "--sentences", str(tmp_path / "sentences.jsonl"),
        "--seen", str(tmp_path / "seen.json"),
        typed="x\nx\n",
    )  # fmt: skip
    assert code == 0, out
    assert asked_at_first_read == [True]
    assert fake_writer.calls[:2] == [first, second]
