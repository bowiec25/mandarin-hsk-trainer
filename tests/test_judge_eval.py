"""The judge's eval script and the HSK labelled cases (ADR 0007 rule 4).

The real eval needs `claude` and is run by hand; here a fake judge stands in.
"""

import json
from pathlib import Path

from hsk_trainer.quiz_setup import JUDGE_SUBJECT
from quizkit.blocks.grader import grade
from quizkit.blocks.judge import Verdict
from quizkit.blocks.judge.eval import EvalCase, load_cases, main, run_eval

ROOT = Path(__file__).parent.parent
HSK_CASES = ROOT / "tests" / "data" / "judge_eval_hsk.jsonl"
ANSWERS = ROOT / "data" / "generated" / "answers.jsonl"


def case(typed: str, expected: bool, subject: str = "Capitals.") -> EvalCase:
    return EvalCase(
        subject=subject,
        card_id="fr",
        shown={"country": "France"},
        accepted=["Paris"],
        typed=typed,
        expected=expected,
    )


def judge_saying(answers: dict[str, Verdict]):
    return lambda subject: lambda question, typed: answers[typed]


YES = Verdict(correct=True, reason="ok", source="claude")
NO = Verdict(correct=False, reason="no", source="claude")
UNCHECKED = Verdict(correct=False, reason="couldn't check", source="not_checked")


# --- run_eval counting --------------------------------------------------------------


def test_counts_right_wrong_yes_wrong_no_and_not_checked():
    cases = [
        case("a", True),
        case("b", False),
        case("c", False),
        case("d", True),
        case("e", False),
    ]
    verdicts = {"a": YES, "b": NO, "c": YES, "d": NO, "e": UNCHECKED}
    report = run_eval(cases, judge_saying(verdicts), show=lambda s: None)
    assert (report.total, report.right, report.wrong_yes, report.wrong_no) == (
        5,
        2,
        1,
        1,
    )
    assert report.not_checked == 1  # not counted right, even though expected was no
    assert report.passed is False


def test_passes_at_90_percent_with_no_wrong_yes():
    cases = [case(str(i), True) for i in range(9)] + [case("x", True)]
    verdicts = {str(i): YES for i in range(9)} | {"x": NO}
    assert run_eval(cases, judge_saying(verdicts), show=lambda s: None).passed


def test_one_wrong_yes_fails_even_at_high_accuracy():
    cases = [case(str(i), True) for i in range(19)] + [case("x", False)]
    verdicts = {str(i): YES for i in range(19)} | {"x": YES}
    report = run_eval(cases, judge_saying(verdicts), show=lambda s: None)
    assert report.right == 19 and report.wrong_yes == 1
    assert report.passed is False


def test_seconds_is_the_average_per_case():
    ticks = iter([0.0, 2.0, 10.0, 14.0])
    report = run_eval(
        [case("a", True), case("b", True)],
        judge_saying({"a": YES, "b": YES}),
        show=lambda s: None,
        clock=lambda: next(ticks),
    )
    assert report.seconds == 3.0


def test_one_judge_per_subject():
    made: list[str] = []

    def make(subject):
        made.append(subject)
        return lambda q, t: YES

    run_eval(
        [case("a", True, "One."), case("b", True, "One."), case("c", True, "Two.")],
        make,
        show=lambda s: None,
    )
    assert made == ["One.", "Two."]


def test_main_without_claude_reports_couldnt_check_and_fails(capsys):
    """conftest makes `claude` look not installed, so nothing is checked."""
    code = main([str(HSK_CASES), "--limit", "2"])
    out = capsys.readouterr().out
    assert code == 1
    assert "0/2 right" in out
    assert "couldn't check 2" in out
    assert "FAIL" in out


# --- the HSK labelled cases ---------------------------------------------------------


def test_hsk_cases_load_and_cover_both_verdicts():
    cases = load_cases(HSK_CASES)
    assert len(cases) >= 30
    labels = [c.expected for c in cases]
    assert labels.count(True) >= 10 and labels.count(False) >= 10
    assert any("ignore" in c.typed.lower() for c in cases)  # an injection attempt
    assert any("</answer>" in c.typed for c in cases)  # one that tries to close the tag


def test_hsk_cases_use_the_quizs_own_subject():
    assert {c.subject for c in load_cases(HSK_CASES)} == {JUDGE_SUBJECT}


def test_hsk_cases_match_todays_answer_list():
    """If answers.jsonl changes, the cases must be rebuilt, or they test a stale list."""
    answers = {}
    for line in ANSWERS.read_text("utf-8").splitlines():
        row = json.loads(line)
        answers[row["id"]] = row["answers"]
    for c in load_cases(HSK_CASES):
        assert c.accepted == answers[c.card_id], c.card_id


def test_every_hsk_case_is_one_the_list_misses():
    """The judge is only asked when the list says wrong, so that's all worth testing."""
    for c in load_cases(HSK_CASES):
        assert not grade(c.typed, c.accepted).correct, (c.card_id, c.typed)


def test_limit_must_be_positive():
    import pytest

    for bad in ("0", "-5"):
        with pytest.raises(SystemExit):
            main([str(HSK_CASES), "--limit", bad])


# --- per-case rubric (ADR 0012) -----------------------------------------------------

SENTENCE_CASES = ROOT / "tests" / "data" / "judge_eval_sentences.jsonl"


def with_rubric(c: EvalCase, rubric: str) -> dict:
    return {**c.model_dump(), "rubric": rubric}


def test_case_rubric_defaults_to_words():
    assert case("Paris", True).rubric == "words"
    gist = EvalCase.model_validate(with_rubric(case("Paris", True), "gist"))
    assert gist.rubric == "gist"


def test_unknown_rubric_name_is_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EvalCase.model_validate(with_rubric(case("Paris", True), "loose"))


def test_hsk_cases_are_all_word_cases():
    assert {c.rubric for c in load_cases(HSK_CASES)} == {"words"}


def test_main_judges_gist_cases_with_gist_rubric_and_200_chars(tmp_path, monkeypatch):
    """A fake ClaudeJudge records how main makes each judge; no Claude runs."""
    import quizkit.blocks.judge as judge_block
    import quizkit.blocks.judge.eval as judge_eval

    made: list[dict] = []

    def fake_judge(subject, **kwargs):
        made.append({"subject": subject, **kwargs})
        return lambda question, typed: YES

    monkeypatch.setattr(judge_eval, "ClaudeJudge", fake_judge)
    word = case("Paree", True, "Same quiz.").model_dump()
    gist = with_rubric(case("It is Paris.", True, "Same quiz."), "gist")
    cases = tmp_path / "cases.jsonl"
    cases.write_text(json.dumps(word) + "\n" + json.dumps(gist) + "\n", "utf-8")

    assert main([str(cases)]) == 0
    assert len(made) == 2  # same subject, two rubrics: two judges
    words_judge, gist_judge = made
    assert words_judge.get("rubric") in (None, judge_block.WORD_RUBRIC)
    assert words_judge.get("max_chars", 100) == 100
    assert gist_judge["rubric"] == judge_block.GIST_RUBRIC
    assert gist_judge["max_chars"] == 200


def test_sentence_cases_load_as_gist_and_cover_both_verdicts():
    cases = load_cases(SENTENCE_CASES)
    assert len(cases) >= 30
    assert {c.rubric for c in cases} == {"gist"}
    labels = [c.expected for c in cases]
    assert labels.count(True) >= 10 and labels.count(False) >= 10
    assert any("ignore" in c.typed.lower() for c in cases)  # an injection attempt


SENTENCES = ROOT / "data" / "generated" / "sentences.jsonl"


def test_sentence_cases_match_the_banks_english():
    """A case's reference English is the bank's, while the sentence is in the bank.

    The audit (or live play) may remove a sentence: the case still tests the judge,
    so only a changed English line is a failure (rebuild that case).
    """
    bank = {}
    for line in SENTENCES.read_text("utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            for s in row["sentences"]:
                bank[(row["id"], s["hanzi"])] = s["english"]
    for c in load_cases(SENTENCE_CASES):
        key = (c.card_id, c.shown["sentence"])
        if key in bank:
            assert c.accepted == [bank[key]], key


def test_every_sentence_case_is_one_the_grader_misses():
    for c in load_cases(SENTENCE_CASES):
        assert not grade(c.typed, c.accepted).correct, (c.card_id, c.typed)


def test_every_sentence_case_fits_the_gist_limit():
    from quizkit.blocks.judge import GIST_MAX_CHARS

    for c in load_cases(SENTENCE_CASES):
        assert len(c.typed) <= GIST_MAX_CHARS, c.typed


def test_sentence_cases_use_the_translate_modes_subject():
    """The eval must measure the judge exactly as translate mode calls it."""
    from hsk_trainer.quiz_setup import TRANSLATE_SUBJECT

    assert {c.subject for c in load_cases(SENTENCE_CASES)} == {TRANSLATE_SUBJECT}
