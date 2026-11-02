"""Tests for the `hsk` command line (M3 Step 5).

CliRunner plays the quiz with scripted keystrokes: `input="love\\neight\\n"` types two
answers, each followed by Enter. Running out of input = end-of-input (quit).
"""

import functools
import os
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from hsk_trainer.blocks.cedict_cleaner import clean_answer
from hsk_trainer.cli import CARDS_FILE, app
from quizkit.files import load_cards

runner = CliRunner()


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


def cleaned(card) -> list[str]:
    """The answers the quiz really accepts (after the cedict_cleaner), in order."""
    return [kept for a in card.answers for kept in clean_answer(a)]


def right_answers(words: list[str], real_cards) -> list[str]:
    by_id = {c.id: c for c in real_cards}
    return [cleaned(by_id[w])[0] for w in words]


# --- playing a whole quiz ---------------------------------------------------------


def test_all_right_scores_full_marks(real_cards):
    args = ("--band", "1", "--n", "5", "--seed", "1")
    typed = "\n".join(right_answers(deck_words(*args), real_cards)) + "\n"
    code, out = play(*args, typed=typed)
    assert code == 0
    assert out.count("✅") == 5
    assert "Score: 5/5" in out


def test_shows_the_hanzi_being_asked():
    args = ("--band", "1", "--n", "3", "--seed", "2")
    _, out = play(*args, typed="x\nx\nx\n")
    for word in deck_words(*args):
        assert word in out


def test_wrong_answer_shows_the_right_ones(real_cards):
    args = ("--band", "1", "--n", "1", "--seed", "3")
    [word] = deck_words(*args)
    code, out = play(*args, typed="zzzzzzzz\n")
    assert code == 0
    assert "❌" in out
    assert cleaned({c.id: c for c in real_cards}[word])[0] in out
    assert "Score: 0/1" in out


def test_love_and_to_love_both_count_for_ai():
    """Issue #16 "Done when": "love" and "to love" both count as correct for 爱."""
    for typed in ("love", "to love"):
        # Find a seed whose 1-card band-1 deck is 爱 (deterministic, so this is stable).
        seed = next(
            s for s in range(5000) if deck_words("--n", "1", "--seed", str(s)) == ["爱"]
        )
        _, out = play("--n", "1", "--seed", str(seed), typed=typed + "\n")
        assert "✅" in out, typed
        assert "Score: 1/1" in out


def test_typo_is_forgiven_and_noted():
    seed = next(
        s for s in range(5000) if deck_words("--n", "1", "--seed", str(s)) == ["爱"]
    )
    _, out = play("--n", "1", "--seed", str(seed), typed="lvoe\n")
    assert "✅" in out
    assert "typo" in out.lower()


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


def test_end_of_input_quits_and_keeps_score(real_cards):
    args = ("--band", "1", "--n", "5", "--seed", "6")
    first_two = right_answers(deck_words(*args)[:2], real_cards)
    code, out = play(*args, typed="\n".join(first_two) + "\n")  # then input runs out
    assert code == 0
    assert "Stopped after 2 of 5" in out
    assert "Score: 2/2" in out


def test_quit_before_any_answer():
    code, out = play("--n", "3", "--seed", "1", typed="")
    assert code == 0
    assert "Stopped after 0 of 3" in out
    assert "Traceback" not in out


def test_ctrl_c_quits_and_keeps_score(monkeypatch, real_cards):
    args = ("--band", "1", "--n", "3", "--seed", "7")
    first = right_answers(deck_words(*args)[:1], real_cards)[0]
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


@pytest.mark.parametrize("mode", ["char_sentence", "full"])
def test_sentence_modes_not_ready_yet(mode):
    code, out = play("--mode", mode)
    assert code != 0
    assert "sentence" in out.lower()
    assert "Traceback" not in out


def test_unknown_mode_is_refused():
    code, out = play("--mode", "banana")
    assert code != 0
    assert "char_pinyin" in out  # tells you what is allowed


def test_missing_cards_file_says_how_to_fix(tmp_path):
    missing = tmp_path / "nope.jsonl"
    code, out = play("--cards", str(missing))
    assert code == 1
    assert "normalizer" in out
    assert "Traceback" not in out


def test_help_lists_the_options():
    result = runner.invoke(app, ["quiz", "--help"])
    assert result.exit_code == 0
    for opt in ("--band", "--mode", "--n", "--seed"):
        assert opt in result.output


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
        + ["--mode", "char_pinyin", "--n", "2", "--seed", "1"],
        check=False,  # we check returncode ourselves, to show stderr on failure
        input=b"x\nx\n",
        capture_output=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    out = proc.stdout.decode("utf-8")
    assert "Score: 0/2" in out
