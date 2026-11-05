"""Measure the judge on hand-labelled cases (ADR 0007 rule 4). Needs the real `claude`.

    uv run python -m quizkit.blocks.judge.eval <cases.jsonl>
        [--model haiku] [--limit N] [--timeout 15]

Each line of the cases file is one `EvalCase` (the HSK word set: tests/data/judge_eval_hsk.jsonl;
the sentence set, `"rubric": "gist"`: tests/data/judge_eval_sentences.jsonl). It reports how many verdicts were right,
the wrong "yes"es and "no"s, the cases Claude couldn't check, and seconds per call.
Bar to ship: at least 90% right and no wrong "yes" (exit code 0 = bar met, 1 = not).
Run by hand, not in CI; re-run whenever the prompt or the model changes.
"""

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from quizkit.blocks.judge import GIST_MAX_CHARS, GIST_RUBRIC, ClaudeJudge, Judge
from quizkit.models import Question

PASS_RATE = 0.9
RUBRICS = {"gist": GIST_RUBRIC}  # a case's rubric name -> its text ("words" = default)


def _positive(text: str) -> int:
    number = int(text)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, not {number}")
    return number


class EvalCase(BaseModel):
    """One hand-labelled case: the question, what was typed, and the right verdict."""

    model_config = ConfigDict(frozen=True)

    subject: str = Field(min_length=1)
    card_id: str = Field(min_length=1)
    shown: dict[str, str]
    accepted: list[str] = Field(min_length=1)
    typed: str = Field(min_length=1)
    expected: bool
    why: str = ""  # the labeller's note: why this verdict is the right one
    rubric: Literal["words", "gist"] = "words"  # which marking rules (ADR 0012)

    def question(self) -> Question:
        return Question(
            card_id=self.card_id,
            mode="eval",
            shown=self.shown,
            accepted_answers=self.accepted,
        )


class EvalReport(BaseModel):
    """How the judge did on the cases."""

    model_config = ConfigDict(frozen=True)

    total: int
    right: int
    wrong_yes: int  # said yes to an answer that should be rejected (the worst kind)
    wrong_no: int
    not_checked: int  # counted as not right
    seconds: float  # average per case

    @computed_field
    @property
    def passed(self) -> bool:
        return (
            self.total > 0
            and self.right / self.total >= PASS_RATE
            and self.wrong_yes == 0
        )


def load_cases(path: Path) -> list[EvalCase]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [EvalCase.model_validate_json(line) for line in lines if line.strip()]


def run_eval(
    cases: list[EvalCase],
    make_judge: Callable[..., Judge],
    show: Callable[[str], None] = print,
    clock: Callable[[], float] = time.perf_counter,
) -> EvalReport:
    """Judge every case and count how it did.

    One judge per subject and rubric: `make_judge(subject)` for word cases,
    `make_judge(subject, rubric=GIST_RUBRIC)` (the rubric's text) for gist cases.
    """
    judges: dict[tuple[str, str], Judge] = {}
    right = wrong_yes = wrong_no = not_checked = 0
    spent = 0.0
    for case in cases:
        which = (case.subject, case.rubric)
        if which not in judges:
            if case.rubric == "words":
                judges[which] = make_judge(case.subject)
            else:
                judges[which] = make_judge(case.subject, rubric=RUBRICS[case.rubric])
        judge = judges[which]
        start = clock()
        verdict = judge(case.question(), case.typed)
        took = clock() - start
        spent += took
        if verdict.source == "not_checked":
            not_checked += 1
            mark = "?"
        elif verdict.correct == case.expected:
            right += 1
            mark = "✓"
        elif verdict.correct:
            wrong_yes += 1
            mark = "✗ WRONG YES"
        else:
            wrong_no += 1
            mark = "✗ wrong no"
        said = "yes" if verdict.correct else "no"
        want = "yes" if case.expected else "no"
        show(
            f"{mark} {case.card_id} {case.typed!r}: {said} (want {want}, "
            f"{took:.1f} s) {verdict.reason}"
        )
    total = len(cases)
    return EvalReport(
        total=total,
        right=right,
        wrong_yes=wrong_yes,
        wrong_no=wrong_no,
        not_checked=not_checked,
        seconds=spent / total if total else 0.0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the judge on labelled cases.")
    parser.add_argument("cases", type=Path, help="a JSON Lines file of EvalCase")
    parser.add_argument("--model", default="haiku")
    parser.add_argument(
        "--limit", type=_positive, default=None, help="only the first N"
    )
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)[: args.limit]

    def make_judge(subject: str, rubric: str | None = None) -> Judge:
        if rubric == GIST_RUBRIC:
            return ClaudeJudge(
                subject,
                model=args.model,
                timeout=args.timeout,
                rubric=GIST_RUBRIC,
                max_chars=GIST_MAX_CHARS,
            )
        return ClaudeJudge(subject, model=args.model, timeout=args.timeout)

    report = run_eval(cases, make_judge)
    print(
        f"\n{args.model}: {report.right}/{report.total} right "
        f"({report.right / max(report.total, 1):.0%}), wrong yes {report.wrong_yes}, "
        f"wrong no {report.wrong_no}, couldn't check {report.not_checked}, "
        f"{report.seconds:.1f} s per call -> {'PASS' if report.passed else 'FAIL'} "
        f"(bar: {PASS_RATE:.0%} right, no wrong yes)"
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    for stream in (
        sys.stdout,
        sys.stderr,
    ):  # Windows pipes can't print non-ASCII otherwise
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
