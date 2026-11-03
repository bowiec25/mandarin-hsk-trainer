"""The judge's eval script and the HSK labelled cases (ADR 0007 rule 4).

The real eval needs `claude` and is run by hand; here a fake judge stands in.
"""

import json
from pathlib import Path

from hsk_trainer.cli import JUDGE_SUBJECT
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
