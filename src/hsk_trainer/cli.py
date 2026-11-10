"""Command-line entry point: `uv run hsk quiz --band 1 --mode char --n 10`.

Not a block: it is the thin shell that wires the blocks to the keyboard and screen
(cards.jsonl + answers.jsonl -> deck_builder -> engine's run_quiz). One answer list
decides what counts (ADR 0006): the answers in data/generated/answers.jsonl. An answer
the list misses goes to the Claude judge (ADR 0007), unless --no-judge. The sentence
modes show an example sentence from the bank (ADR 0011, `sentence_bank`). The translate
modes ask for a whole sentence's meaning, graded for the gist (ADR 0012).
"""

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from hsk_trainer.blocks.answer_writer import ANSWERS_FILE, AnswerFileError, load_answers
from hsk_trainer.blocks.live_sentences import LiveSentences
from hsk_trainer.blocks.sentence_bank import SEEN_FILE, SentenceBank
from hsk_trainer.blocks.sentence_writer import (
    SENTENCES_FILE,
    Sentence,
    SentenceFileError,
)
from hsk_trainer.modes import HSK_MODES
from quizkit.blocks.deck_builder import build_deck
from quizkit.blocks.engine import Attempt, QuizSession, run_quiz
from quizkit.blocks.grader import GradeSettings, clean
from quizkit.blocks.judge import GIST_MAX_CHARS, GIST_RUBRIC, ClaudeJudge
from quizkit.blocks.progress_store import ProgressFileError, ProgressStore
from quizkit.files import load_cards
from quizkit.models import Card, Judge, Question, Verdict
from quizkit.modes import Mode
from quizkit.progress import save_attempt

# Found from this file, so `hsk` works from any folder (src/hsk_trainer/cli.py -> root).
# Assumes it runs from the repo (`uv run hsk`), not from an installed wheel.
ROOT = Path(__file__).resolve().parents[2]
CARDS_FILE = ROOT / "data" / "processed" / "cards.jsonl"
JUDGE_CACHE = ROOT / "data" / "judge_cache.jsonl"  # gitignored: verdicts, not source
PROGRESS_FILE = ROOT / "data" / "progress.db"  # gitignored: your own progress
SETTINGS = GradeSettings()
# Sentences: no typo forgiveness. A 1-2 letter change can flip the meaning
# ("I don't like" -> "I do like"); near-misses go to the gist judge instead.
TRANSLATE_SETTINGS = GradeSettings(allow_typos=False)
# The only HSK part of the judge: what the quiz is about (ADR 0007).
JUDGE_SUBJECT = (
    "Chinese vocabulary for learners of HSK 3.0, bands 1-3. The learner sees a "
    "Chinese word and types its English meaning."
)
# The translate modes' subject; the sentence eval set uses the same one (ADR 0012).
TRANSLATE_SUBJECT = (
    "Chinese example sentences for learners of HSK 3.0, bands 1-3. The learner sees "
    "a Chinese sentence and types what it means in English."
)

PLAYABLE_MODES = tuple(HSK_MODES)
SENTENCE_FIELDS = ("sentence", "sentence_pinyin")  # from the bank, not the card
SHOW_ANSWERS = 4  # how many accepted answers to show after a wrong one

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
    if mode in PLAYABLE_MODES:
        return mode
    raise typer.BadParameter(
        f"{mode!r} is not a mode. Try: {', '.join(PLAYABLE_MODES)}."
    )


class _Sentences:
    """The sentence part of a question: shown under the word, its English after the
    answer (ADR 0011). New ones from Claude or banked ones, via live_sentences. Only
    used by the sentence modes."""

    def __init__(
        self,
        live: LiveSentences,
        fields: list[str],
        questions: list[Question],
        cards: dict[str, Card] | None = None,
    ) -> None:
        self.live = live
        self.fields = fields  # which of SENTENCE_FIELDS the mode shows, in order
        self.questions = questions
        self.cards = cards or {}  # for the word line after a translation
        self.current: Sentence | None = None
        self.revealed = False  # the English was shown already (self-marking)
        self.stopped = False  # Ctrl-C at the y/n prompt: stop after this answer
        self.told_fallback = False  # the 'mark it yourself' reason, said once
        self.at = 0  # questions shown so far (the engine asks them in turn)

    def start(self) -> None:
        """Before the first question: start on its sentence."""
        if self.questions:
            self.live.prepare(self.questions[0].card_id)

    def _fetch(self, question: Question) -> Sentence | None:
        shown = self.live.sentence_for(question.card_id)
        self.current = shown.sentence
        self.revealed = False
        if shown.note:
            print(f"   ({shown.note})")
        # While you answer, the next word's sentence is being written.
        self.at += 1
        if self.at < len(self.questions):
            self.live.prepare(self.questions[self.at].card_id)
        return self.current

    def translate(self, question: Question) -> Question | None:
        """The engine's `prepare` for the translate modes: the word's question becomes
        its sentence's, with the English as the answer. No usable sentence = skip."""
        sentence = self._fetch(question)
        if sentence is None or not clean(sentence.english, SETTINGS):
            word = next(iter(question.shown.values()))
            print(f"\n   (skipped {word}: no example sentence yet)")
            return None
        shown = {"sentence": sentence.hanzi}
        if "sentence_pinyin" in self.fields:
            shown["sentence_pinyin"] = sentence.pinyin
        return Question(
            card_id=question.card_id,
            mode=question.mode,
            shown=shown,
            accepted_answers=[sentence.english],
        )

    def self_mark(self, question: Question, typed: str) -> Verdict:
        """A Judge without Claude: show the English, the learner says if they got it."""
        print(f"   = {question.accepted_answers[0]}")
        self.revealed = True
        while True:
            try:
                reply = _read("   Did you get the gist? (y/n) ")
            except KeyboardInterrupt:  # keep this answer (unmarked), then stop
                print()
                reply, self.stopped = None, True
            if reply is None:  # end of input: not marked, so not right
                return Verdict(correct=False, reason="not marked", source="not_checked")
            reply = reply.strip().lower()
            if reply in ("y", "yes"):
                return Verdict(correct=True, reason="you got the gist", source="self")
            if reply in ("n", "no"):
                return Verdict(correct=False, reason="you missed it", source="self")

    def after_translation(self) -> None:
        """After a translation: the English, the pinyin if it was hidden, the word."""
        if self.current is None:
            return
        if not self.revealed:
            print(f"   = {self.current.english}")
        if "sentence_pinyin" not in self.fields:
            print(f"   {self.current.pinyin}")
        card = self.cards.get(self.questions[self.at - 1].card_id)
        if card is not None:
            meaning = "; ".join(card.answers[:SHOW_ANSWERS])
            print(
                f"   word: {card.fields['hanzi']} ({card.fields['pinyin']}) = {meaning}"
            )

    def show(self, question: Question) -> None:
        if self._fetch(question) is None:
            print("   (no example sentence yet for this word)")
            return
        print(f"   {self.current.hanzi}")
        if "sentence_pinyin" in self.fields:
            print(f"   {self.current.pinyin}")

    def finish(self) -> None:
        """End of the quiz: save sentences still being written."""
        for note in self.live.finish():
            print(f"   ({note})")

    def after(self) -> None:
        if self.current is not None:
            print(f"   = {self.current.english}")


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


def _readable(question: Question) -> dict[str, str]:
    """Each accepted answer, in the grader's normalised form -> as written for people.

    The grader compares normalised text ("haven't" -> "havent", "to love" -> "love");
    showing that would teach misspellings. Same order and de-duplication as the grader.
    """
    readable: dict[str, str] = {}
    for answer in question.accepted_answers:
        key = clean(answer, SETTINGS)
        if key and key not in readable:
            readable[key] = answer
    return readable


def _with_answers(cards: list[Card], answers_file: Path) -> list[Card]:
    """Each card with its answers from answers.jsonl (the one answer list, ADR 0006).

    load_answers checks the file with the writer's own checker; Card re-checks each
    card. Raises ValueError (AnswerFileError is one) for a bad or incomplete file.
    """
    answers = load_answers(answers_file, cards)
    return [
        Card.model_validate({**c.model_dump(), "answers": answers[c.id]}) for c in cards
    ]


def _tell(attempt: Attempt) -> None:
    g, verdict = attempt.grade, attempt.verdict
    readable = _readable(attempt.question)
    if g.correct and g.typo:
        print(f"✅ close enough (typo): {readable.get(g.matched, g.matched)}")
    elif g.correct:
        print("✅")
    elif verdict is not None and verdict.correct and verdict.source == "self":
        print(f"✅ {verdict.reason}")
    elif verdict is not None and verdict.correct:
        print(f"✅ accepted by the Claude judge: {verdict.reason}")
    else:
        answers = list(readable.values())
        more = " …" if len(answers) > SHOW_ANSWERS else ""
        print(f"❌ {'; '.join(answers[:SHOW_ANSWERS])}{more}")
        if verdict is not None and verdict.source == "not_checked":
            print(f"   (judge {verdict.reason})")
        elif verdict is not None:
            print(f"   judge: {verdict.reason}")


def _tell_translation(attempt: Attempt) -> None:
    g, verdict = attempt.grade, attempt.verdict
    if g.correct:
        print("✅ close enough (typo)" if g.typo else "✅")
    elif verdict is not None and verdict.correct:
        if verdict.source == "self":
            print(f"✅ {verdict.reason}")
        else:
            print(f"✅ accepted by the Claude judge: {verdict.reason}")
    else:
        print("❌")
        if verdict is not None and verdict.source in ("claude", "cache"):
            print(f"   judge: {verdict.reason}")
        elif verdict is not None and verdict.source == "not_checked":
            print(f"   ({verdict.reason})")


def _or_self_mark(judge: Judge, part: "_Sentences") -> Judge:
    """Claude's verdict, or the learner's own when Claude couldn't check (ADR 0012)."""

    def judged(question: Question, typed: str) -> Verdict:
        verdict = judge(question, typed)
        if verdict.source != "not_checked":
            return verdict
        if not part.told_fallback:  # the reason once, not on every question
            print(f"   (the judge couldn't check: {verdict.reason})")
            part.told_fallback = True
        print("   Mark it yourself:")
        return part.self_mark(question, typed)

    return judged


class _Saving:
    """Saves each marked answer and moves its box (ADR 0013); counts the moves."""

    def __init__(self, store: ProgressStore, skill: str) -> None:
        self.store, self.skill = store, skill
        self.up = self.back = 0
        self.failed = False

    def save(self, attempt: Attempt) -> None:
        if self.failed:  # told once already: the rest of this quiz isn't saved
            return
        try:
            old, new = save_attempt(self.store, attempt, self.skill, datetime.now(UTC))
        except ProgressFileError as err:
            print(f"   ⚠️ Couldn't save your progress: {err}")
            print("   The rest of this quiz won't be saved.")
            self.failed = True
            return
        if new is not None and not attempt.correct:
            self.back += 1
        elif new is not None and (old is None or new.box > old.box):
            self.up += 1

    def summary(self) -> str | None:
        if not (self.up or self.back):
            return None
        word = "word" if self.up == 1 else "words"
        return f"Boxes: {self.up} {word} moved up, {self.back} back to box 1."


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
    if cards is None:  # looked up now, not at import, so tests can point it elsewhere
        cards = CARDS_FILE
        if not cards.exists():
            _fail(
                f"No cards file at {cards}.",
                f"Make it from {ROOT}: uv run python -m hsk_trainer.blocks.normalizer",
            )
    elif not cards.exists():
        _fail(f"No cards file at {cards}.")
    answers = answers or ANSWERS_FILE

    wanted = HSK_MODES[mode]
    translating = wanted.answer_from == "sentence"
    from_bank = [f for f in wanted.show if f in SENTENCE_FIELDS]
    # The card has no sentence fields: they come from the bank as each word is shown.
    # A translate mode's deck is of word questions, turned into sentences one by one.
    on_card = [f for f in wanted.show if f not in from_bank] or ["hanzi"]
    shown = Mode(name=wanted.name, show=on_card, skill=wanted.skill)
    sentence_part: _Sentences | None = None
    saving: _Saving | None = None
    try:
        all_cards = load_cards(cards)
        # Only this band's cards: a bad line in another band doesn't block this quiz.
        in_band = [c for c in all_cards if c.level == band]
        playable = _with_answers(in_band, answers)
        schedule = None
        if save:  # due words first, then new ones (ADR 0013)
            store = ProgressStore(progress or PROGRESS_FILE)
            saving = _Saving(store, wanted.skill)
            schedule = {cid: b.due for cid, b in store.boxes(wanted.skill).items()}
        questions = build_deck(
            playable, shown, n, levels=[band], seed=seed, schedule=schedule
        )
        # The bank knows every card, so other bands' lines stay as they are.
        if from_bank:
            bank = SentenceBank(
                all_cards, path=sentences or SENTENCES_FILE, seen_path=seen or SEEN_FILE
            )
            sentences_live = LiveSentences(
                bank, all_cards, enabled=live, before_waiting=_writing
            )
            by_id = {c.id: c for c in playable}
            sentence_part = _Sentences(sentences_live, from_bank, questions, by_id)
        # Up-front data check (a card nobody can answer), kept apart from run_quiz so a
        # ValueError mid-quiz is never mislabelled as a bad file.
        QuizSession(questions, settings=SETTINGS)
    except ProgressFileError as err:  # your progress file (a ValueError too)
        _fail(
            f"Can't use your progress file {progress or PROGRESS_FILE}:",
            str(err),
            "Nothing was changed. To practise anyway: add --no-save.",
        )
    except SentenceFileError as err:  # the bank (a ValueError: caught first)
        _fail(
            f"Can't read the sentence bank {sentences or SENTENCES_FILE}:",
            str(err),
            "Restore it with git checkout, or fix the line it names.",
        )
    except (ValidationError, ValueError) as err:  # bad or partial data file
        hint = []
        if answers == ANSWERS_FILE and isinstance(err, AnswerFileError):
            hint = [  # the real file is committed, so this is a broken checkout
                "Restore it with git checkout, or fix it with:",
                "uv run python -m hsk_trainer.blocks.answer_writer",
            ]
        _fail(f"Can't build a quiz from {cards} and {answers.name}:", str(err), *hint)
    except OSError as err:  # a data file that can't be opened
        _fail(f"Can't read the quiz files: {err}")

    if len(questions) < n:
        print(
            f"Only {len(questions)} band-{band} words, so the quiz has {len(questions)}."
        )
    task = (
        "Type what each sentence means in English"
        if translating
        else "Type the meaning in English"
    )
    print(f"Band {band}, {len(questions)} words. {task}; Ctrl-C stops.")

    # run_quiz treats Ctrl-C anywhere in its loop as a quit, so the score is kept.
    judge_fn: Judge | None = (
        ClaudeJudge(JUDGE_SUBJECT, cache_file=JUDGE_CACHE, before_asking=_asking)
        if judge and not translating
        else None
    )
    ask, tell = _ask, _tell
    prepare = None
    settings = SETTINGS
    if translating and sentence_part is not None:  # whole sentences (ADR 0012)
        part = sentence_part
        part.start()
        prepare = part.translate
        settings = TRANSLATE_SETTINGS
        judge_fn = (
            _or_self_mark(
                ClaudeJudge(
                    TRANSLATE_SUBJECT,
                    cache_file=JUDGE_CACHE,
                    before_asking=_asking,
                    rubric=GIST_RUBRIC,
                    max_chars=GIST_MAX_CHARS,
                ),
                part,
            )
            if judge
            else part.self_mark
        )

        def ask(question: Question) -> str | None:
            if part.stopped:  # Ctrl-C at the last y/n: that answer is kept
                return None
            print()
            for text in question.shown.values():
                print(text)
            return _read()

        def tell(attempt: Attempt) -> None:
            _tell_translation(attempt)
            part.after_translation()

    elif sentence_part is not None:  # the sentence modes: a sentence under each word
        part = sentence_part
        part.start()

        def ask(question: Question) -> str | None:
            _show(question)
            part.show(question)
            return _read()

        def tell(attempt: Attempt) -> None:
            _tell(attempt)
            part.after()

    if saving is not None:  # save each answer as soon as it's marked
        progress_saver, shown_tell = saving, tell

        def tell(attempt: Attempt) -> None:
            shown_tell(attempt)
            progress_saver.save(attempt)

    result = run_quiz(
        questions,
        ask=ask,
        tell=tell,
        settings=settings,
        judge=judge_fn,
        prepare=prepare,
    )
    if sentence_part is not None:
        sentence_part.finish()

    print()
    if result.skipped:
        print(f"Skipped {result.skipped} with no example sentence.")
    if not result.finished:
        print(f"Stopped after {result.answered + result.skipped} of {result.total}.")
    if result.answered == 0 and result.skipped:
        why = "Claude couldn't write any just now" if live else "try --live"
        print(f"Nothing to score: no word had a sentence ({why}).")
    else:
        print(f"Score: {result.correct}/{result.answered}")
    if saving is not None and (moved := saving.summary()):
        print(moved)


def _utf8_output() -> None:
    """Windows pipes default to an old code page that can't print 爱 or ài."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main() -> None:
    _utf8_output()
    app()
