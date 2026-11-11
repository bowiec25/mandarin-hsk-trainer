"""Command-line entry point: `uv run hsk quiz --band 1 --mode char --n 10`.

Not a block: the thin shell that wires the quiz to the keyboard and screen. What a
quiz needs (deck, judge, sentences, saving) is built by the shared HSK setup,
`quiz_setup.py` (ADR 0014), which the web page uses too; this file only prints and
reads. One answer list decides what counts (ADR 0006); an answer it misses goes to the
Claude judge (ADR 0007), unless --no-judge. The sentence modes show an example sentence
(ADR 0011); the translate modes ask for a sentence's meaning, graded for the gist
(ADR 0012). Answers are saved in Leitner boxes (ADR 0013), unless --no-save.
"""

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from hsk_trainer import quiz_setup
from hsk_trainer.quiz_setup import (
    GIST_QUESTION,
    GOT_THE_GIST,
    MISSED_IT,
    NO_SENTENCE,
    NOT_MARKED,
    PLAYABLE_MODES,
    QuizFiles,
    QuizOptions,
    SentencePart,
    SetupError,
    build_quiz,
    describe,
    end_lines,
    mode_problem,
    skip_note,
)
from quizkit.blocks.engine import Attempt, run_quiz
from quizkit.blocks.judge import ClaudeJudge
from quizkit.models import Judge, Question, Verdict
from quizkit.progress import SkillStats

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
            print(f"\n   ({skip_note(self.part.skipped)})")
        return ready

    def show(self, question: Question) -> None:
        sentence = self.part.fetch(question)
        self._note()
        if sentence is None:
            print(f"   ({NO_SENTENCE})")
            return
        for line in self.part.lines(sentence):
            print(f"   {line}")

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


def _stats_lines(s: SkillStats, label: dict[str, str]) -> list[str]:
    if quiz_setup.nothing_yet(s):
        return ["    Nothing yet."]
    boxes = " · ".join(f"box {b}: {n}" for b, n in quiz_setup.box_counts(s))
    lines = [f"    new: {s.new} · {boxes} · due now: {s.due}"]
    lines.append(f"    last 7 days: {quiz_setup.week_line(s)}")
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
    given = {"cards": cards, "progress": progress}  # as `quiz` does
    files = QuizFiles(**{name: path for name, path in given.items() if path})
    try:
        report = quiz_setup.gather_stats(files, band)
    except SetupError as err:
        _fail(*err.lines)
    if report is None:
        print("No progress saved yet: play `hsk quiz` (it saves unless --no-save).")
        return
    out: list[str] = []
    for b in report:
        out.append(f"Band {b.band} · {b.words} words")
        for s in b.skills:
            out.append(f"  {s.skill} ({', '.join(s.modes)})")
            out.extend(_stats_lines(s.stats, b.label))
    print("\n".join(out))


WEB_PAGE = Path(__file__).with_name("web_app.py")
# 127.0.0.1, not "localhost": on Windows a check of "localhost" tries ::1 first and
# waits ~2 s per refused address. Still this computer only.
WEB_HOST, WEB_PORT = "127.0.0.1", 8501
WEB_URL = f"http://{WEB_HOST}:{WEB_PORT}"
# Local only, no usage data to Streamlit, no "Deploy" button; .streamlit/config.toml
# says the same. Headless: Streamlit doesn't open the browser (we do, once the page is
# up) and doesn't ask for an email on its first run (that crashed without a keyboard).
WEB_FLAGS = [
    f"--server.address={WEB_HOST}",
    f"--server.port={WEB_PORT}",
    "--server.headless=true",
    "--browser.gatherUsageStats=false",
    "--client.toolbarMode=minimal",
]
WEB_WAIT = 30.0  # seconds to wait for the page to come up before giving up on it


def _web_is_up() -> bool:
    """Is something answering on the page's address?"""
    try:
        with socket.create_connection((WEB_HOST, WEB_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_for_web(process: subprocess.Popen) -> bool:
    """Wait until the page is up (True), or Streamlit stopped / took too long."""
    deadline = time.monotonic() + WEB_WAIT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        if _web_is_up():
            return True
        time.sleep(0.2)
    return False


def _stop(process: subprocess.Popen) -> None:
    """After Ctrl-C: give Streamlit 10 s to finish, then stop it (also on a second
    Ctrl-C), so no copy is left holding the address."""
    try:
        process.wait(timeout=10)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        process.kill()
        process.wait()


@app.command()
def web() -> None:
    """Open the quiz as a web page in your browser (on this computer only, ADR 0014).
    Same quiz and saved progress as `hsk quiz`. Ctrl-C here stops it."""
    if _web_is_up():  # e.g. an `hsk web` left running in another window
        _fail(
            f"Something is already running at {WEB_URL}.",
            "If it's the quiz, just open that page; otherwise stop it first.",
        )
    command = [sys.executable, "-m", "streamlit", "run", str(WEB_PAGE), *WEB_FLAGS]
    # From the repo root, so Streamlit finds .streamlit/config.toml.
    process = subprocess.Popen(command, cwd=quiz_setup.ROOT)
    try:
        if _wait_for_web(process):
            print(f"The quiz is open at {WEB_URL} (Ctrl-C here stops it).", flush=True)
            webbrowser.open(WEB_URL)
        elif process.poll() is None:  # still starting after WEB_WAIT: say where
            print(
                f"Streamlit is slow to start: open {WEB_URL} once it's ready.",
                flush=True,
            )
        code = process.wait()
    except KeyboardInterrupt:  # Streamlit gets the Ctrl-C too: let it finish
        _stop(process)
        return
    if code:
        raise typer.Exit(code)


def _utf8_output() -> None:
    """Windows pipes default to an old code page that can't print 爱 or ài."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main() -> None:
    _utf8_output()
    app()
