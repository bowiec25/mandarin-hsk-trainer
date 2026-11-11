"""Command-line entry point: `uv run hsk quiz --band 1 --mode char --n 10`.

Not a block: the thin shell that wires the quiz to the keyboard and screen. What a
quiz needs (deck, judge, sentences, saving) is built by the shared HSK setup,
`quiz_setup.py` (ADR 0014), which the web page uses too; this file only prints and
reads. One answer list decides what counts (ADR 0006); an answer it misses goes to the
Claude judge (ADR 0007), unless --no-judge. The sentence modes show an example sentence
(ADR 0011); the translate modes ask for a sentence's meaning, graded for the gist
(ADR 0012). Answers are saved in Leitner boxes (ADR 0013), unless --no-save.
"""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from hsk_trainer import quiz_setup
from hsk_trainer.modes import HSK_MODES
from hsk_trainer.quiz_setup import (
    GIST_QUESTION,
    GOT_THE_GIST,
    MISSED_IT,
    NOT_MARKED,
    PLAYABLE_MODES,
    RULE,
    QuizFiles,
    QuizOptions,
    SentencePart,
    SetupError,
    build_quiz,
    describe,
    end_lines,
    mode_problem,
    progress_file,
)
from quizkit.blocks.engine import Attempt, run_quiz
from quizkit.blocks.judge import ClaudeJudge
from quizkit.blocks.progress_store import ProgressStore
from quizkit.files import load_cards
from quizkit.models import Judge, Question, Verdict
from quizkit.progress import SkillStats, skill_stats

app = typer.Typer(
    help="HSK 3.0 vocab trainer (bands 1-3).",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)


@app.callback()
def _root() -> None:
    """HSK 3.0 vocab trainer (bands 1-3)."""  # keeps `quiz` a named subcommand


def _check_mode(mode: str) -> str:
    if problem := mode_problem(mode):
        raise typer.BadParameter(problem)
    return mode


def _show(question: Question) -> None:
    print()
    print("   ".join(question.shown.values()))


def _read(prompt: str = "> ") -> str | None:
    """The typed answer; end-of-input = quit (None)."""
    try:
        return input(prompt)
    except EOFError:
        print()
        return None


def _ask(question: Question) -> str | None:
    """Show the word, read the typed answer. End-of-input = quit (None).

    Ctrl-C needs nothing here: run_quiz treats it as a quit wherever it lands."""
    _show(question)
    return _read()


def _print_described(attempt: Attempt, translating: bool) -> None:
    headline, details = describe(attempt, translating)
    print(headline)
    for line in details:
        print(f"   {line}")


def _tell(attempt: Attempt) -> None:
    _print_described(attempt, translating=False)


def _tell_translation(attempt: Attempt) -> None:
    _print_described(attempt, translating=True)


class _OnScreen:
    """The terminal side of the sentence part: prints its notes and lines, and asks
    "Did you get the gist?" inside marking (a terminal can wait there; ADR 0014)."""

    def __init__(self, part: SentencePart) -> None:
        self.part = part
        self.stopped = False  # Ctrl-C at the y/n prompt: stop after this answer
        self.told_fallback = False  # the 'mark it yourself' reason, said once

    def _note(self) -> None:
        if self.part.note:
            print(f"   ({self.part.note})")

    def translate(self, question: Question) -> Question | None:
        """The engine's `prepare`: the shared translate, plus its notes."""
        ready = self.part.translate(question)
        self._note()
        if ready is None:
            print(f"\n   (skipped {self.part.skipped}: no example sentence yet)")
        return ready

    def show(self, question: Question) -> None:
        sentence = self.part.fetch(question)
        self._note()
        if sentence is None:
            print("   (no example sentence yet for this word)")
            return
        print(f"   {sentence.hanzi}")
        if "sentence_pinyin" in self.part.fields:
            print(f"   {sentence.pinyin}")

    def self_mark(self, question: Question, typed: str) -> Verdict:
        """A Judge without Claude: show the English, the learner says if they got it."""
        print(f"   = {question.accepted_answers[0]}")
        self.part.revealed = True
        while True:
            try:
                reply = _read(f"   {GIST_QUESTION} (y/n) ")
            except KeyboardInterrupt:  # keep this answer (unmarked), then stop
                print()
                reply, self.stopped = None, True
            if reply is None:  # end of input: not marked, so not right
                return NOT_MARKED
            reply = reply.strip().lower()
            if reply in ("y", "yes"):
                return GOT_THE_GIST
            if reply in ("n", "no"):
                return MISSED_IT

    def or_self_mark(self, judge: Judge) -> Judge:
        """Claude's verdict, or the learner's own when Claude couldn't check."""

        def judged(question: Question, typed: str) -> Verdict:
            verdict = judge(question, typed)
            if verdict.source != "not_checked":
                return verdict
            if not self.told_fallback:  # the reason once, not on every question
                print(f"   (the judge couldn't check: {verdict.reason})")
                self.told_fallback = True
            print("   Mark it yourself:")
            return self.self_mark(question, typed)

        return judged

    def after_translation(self) -> None:
        for line in self.part.after_translation():
            print(f"   {line}")

    def after(self) -> None:
        if self.part.current is not None:
            print(f"   = {self.part.current.english}")

    def finish(self) -> None:
        for note in self.part.finish():
            print(f"   ({note})")


def _asking() -> None:
    print("   asking the judge…", flush=True)


def _writing() -> None:
    print("   writing a sentence…", flush=True)


def _fail(*lines: str) -> NoReturn:
    for line in lines:
        print(line, file=sys.stderr)
    raise typer.Exit(1)


@app.command()
def quiz(
    band: Annotated[
        int, typer.Option(min=1, max=3, help="HSK band: only its new words.")
    ] = 1,
    mode: Annotated[
        str,
        typer.Option(
            callback=_check_mode, help=f"What to show: {', '.join(PLAYABLE_MODES)}."
        ),
    ] = "char",
    n: Annotated[int, typer.Option("--n", min=1, help="How many words.")] = 10,
    seed: Annotated[
        int | None, typer.Option(help="Same seed, same words (for replays).")
    ] = None,
    cards: Annotated[Path | None, typer.Option(hidden=True)] = None,
    answers: Annotated[Path | None, typer.Option(hidden=True)] = None,
    sentences: Annotated[Path | None, typer.Option(hidden=True)] = None,
    seen: Annotated[Path | None, typer.Option(hidden=True)] = None,
    progress: Annotated[Path | None, typer.Option(hidden=True)] = None,
    save: Annotated[
        bool,
        typer.Option(
            "--save/--no-save",
            help="Save your answers and Leitner boxes (data/progress.db), and deal "
            "due words first. --no-save = practise without either.",
        ),
    ] = True,
    judge: Annotated[
        bool,
        typer.Option(
            "--judge/--no-judge",
            help="Ask Claude about answers the list misses (needs `claude`, online).",
        ),
    ] = True,
    live: Annotated[
        bool,
        typer.Option(
            "--live/--no-live",
            help="Sentence modes: new sentences from Claude as you play, saved to the "
            "bank (needs `claude`, online). --no-live = banked sentences only.",
        ),
    ] = True,
) -> None:
    """Quiz yourself: see a word (or, in the translate modes, a sentence), type its
    English meaning. Ctrl-C stops (score kept)."""
    given = {"cards": cards, "answers": answers, "sentences": sentences}
    given |= {"seen": seen, "progress": progress}
    files = QuizFiles(**{name: path for name, path in given.items() if path})
    options = QuizOptions(
        band=band, mode=mode, n=n, seed=seed, judge=judge, live=live, save=save
    )
    try:
        hsk = build_quiz(
            options,
            files,
            judge_class=ClaudeJudge,
            before_asking=_asking,
            before_writing=_writing,
        )
    except SetupError as err:
        _fail(*err.lines)

    questions = hsk.questions
    if len(questions) < n:
        print(
            f"Only {len(questions)} band-{band} words, so the quiz has {len(questions)}."
        )
    task = (
        "Type what each sentence means in English"
        if hsk.translating
        else "Type the meaning in English"
    )
    print(f"Band {band}, {len(questions)} words. {task}; Ctrl-C stops.")

    # run_quiz treats Ctrl-C anywhere in its loop as a quit, so the score is kept.
    ask, tell = _ask, _tell
    judge_fn = hsk.judge
    prepare = None
    screen = _OnScreen(hsk.sentences) if hsk.sentences is not None else None
    if hsk.prepare is not None and screen is not None:  # whole sentences (ADR 0012)
        on = screen
        on.part.start()
        prepare = on.translate  # the shared hsk.prepare, plus its notes on screen
        judge_fn = on.or_self_mark(hsk.judge) if hsk.judge else on.self_mark

        def ask(question: Question) -> str | None:
            if on.stopped:  # Ctrl-C at the last y/n: that answer is kept
                return None
            print()
            for text in question.shown.values():
                print(text)
            return _read()

        def tell(attempt: Attempt) -> None:
            _tell_translation(attempt)
            on.after_translation()

    elif screen is not None:  # the sentence modes: a sentence under each word
        on = screen
        on.part.start()

        def ask(question: Question) -> str | None:
            _show(question)
            on.show(question)
            return _read()

        def tell(attempt: Attempt) -> None:
            _tell(attempt)
            on.after()

    saver = hsk.saver
    if saver is not None:  # save each answer as soon as it's final
        shown_tell = tell

        def tell(attempt: Attempt) -> None:
            # Saved first: a Ctrl-C while the result shows can't lose it.
            problem = saver.save(attempt)
            shown_tell(attempt)
            if problem:
                print(f"   {problem}")

    result = run_quiz(
        questions,
        ask=ask,
        tell=tell,
        settings=hsk.settings,
        judge=judge_fn,
        prepare=prepare,
    )
    if screen is not None:
        screen.finish()

    print()
    for line in end_lines(result, live, saver):
        print(line)


def _skills() -> dict[str, list[str]]:
    """Each skill and the modes that practise it, in mode order (from config)."""
    skills: dict[str, list[str]] = {}
    for m in HSK_MODES.values():
        skills.setdefault(m.skill, []).append(m.name)
    return skills


def _stats_lines(s: SkillStats, label: dict[str, str]) -> list[str]:
    if s.new == s.cards and not (s.recent_answered or s.recent_unchecked):
        return ["    Nothing yet."]
    last = max([len(RULE.waits), *s.by_box])  # a box past the rule's last: show it
    boxes = " · ".join(f"box {b}: {s.by_box.get(b, 0)}" for b in range(1, last + 1))
    lines = [f"    new: {s.new} · {boxes} · due now: {s.due}"]
    if s.recent_answered:
        pct = 100 * s.recent_right // s.recent_answered  # rounded down: 199/200 = 99%
        week = f"{s.recent_right}/{s.recent_answered} right ({pct}%)"
    else:
        week = "no checked answers"
    if s.recent_unchecked:
        week += f" (+{s.recent_unchecked} not checked)"
    lines.append(f"    last 7 days: {week}")
    if s.most_missed:
        missed = ", ".join(f"{label.get(c, c)} ×{n}" for c, n in s.most_missed)
        lines.append(f"    most missed: {missed}")
    return lines


@app.command()
def stats(
    band: Annotated[
        int | None,
        typer.Option(min=1, max=3, help="Only this HSK band (default: all three)."),
    ] = None,
    cards: Annotated[Path | None, typer.Option(hidden=True)] = None,
    progress: Annotated[Path | None, typer.Option(hidden=True)] = None,
) -> None:
    """How you're doing: words new / in each Leitner box / due now, the last 7 days'
    accuracy and your most-missed words, per band and skill. Changes nothing."""
    progress_path = progress or progress_file()
    # Never make (or set up) the file just to look at it: an empty file is set up by
    # the first quiz that saves.
    if not progress_path.exists() or (
        progress_path.is_file() and progress_path.stat().st_size == 0
    ):
        print("No progress saved yet: play `hsk quiz` (it saves unless --no-save).")
        return
    cards_file = cards or quiz_setup.CARDS_FILE
    try:
        all_cards = load_cards(cards_file)
    except (ValidationError, ValueError, OSError) as err:
        _fail(f"Can't read the cards file {cards_file}:", str(err))
    now = datetime.now(UTC)
    bands = [band] if band is not None else sorted({c.level for c in all_cards})
    skills = _skills()
    out: list[str] = []
    try:
        store = ProgressStore(progress_path)
        for b in bands:
            in_band = [c for c in all_cards if c.level == b]
            # hanzi + pinyin: two readings of one character (还 hái / huán) differ
            label = {
                c.id: " ".join(
                    filter(None, [c.fields.get("hanzi", c.id), c.fields.get("pinyin")])
                )
                for c in in_band
            }
            out.append(f"Band {b} · {len(in_band)} words")
            for skill, modes in skills.items():
                out.append(f"  {skill} ({', '.join(modes)})")
                out.extend(_stats_lines(skill_stats(store, label, skill, now), label))
    except (ValueError, OSError) as err:  # ProgressFileError is a ValueError
        _fail(f"Can't read your progress file {progress_path}:", str(err))
    print("\n".join(out))


WEB_PAGE = Path(__file__).with_name("web_app.py")
# Local only, and no usage data to Streamlit; .streamlit/config.toml says the same.
WEB_FLAGS = ["--server.address=localhost", "--browser.gatherUsageStats=false"]


@app.command()
def web() -> None:
    """Open the quiz as a web page in your browser (on this computer only, ADR 0014).
    Same quiz and saved progress as `hsk quiz`. Ctrl-C here stops it."""
    command = [sys.executable, "-m", "streamlit", "run", str(WEB_PAGE), *WEB_FLAGS]
    try:  # from the repo root, so Streamlit finds .streamlit/config.toml
        done = subprocess.run(command, cwd=quiz_setup.ROOT, check=False)
    except KeyboardInterrupt:
        return
    if done.returncode not in (0, None):
        raise typer.Exit(done.returncode)


def _utf8_output() -> None:
    """Windows pipes default to an old code page that can't print 爱 or ài."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main() -> None:
    _utf8_output()
    app()
