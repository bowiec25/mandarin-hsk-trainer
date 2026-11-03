"""answer_writer: Write, for each card, the English answers a learner might type,
saved to data/generated/answers.jsonl

See SPEC.md in this folder (ADR 0003, ADR 0005, ADR 0006: the quiz's one answer list).
Run by hand: uv run python -m hsk_trainer.blocks.answer_writer --limit 20 [--dry-run]
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from quizkit.blocks.base import BlockSpec
from quizkit.blocks.grader import GradeSettings, clean
from quizkit.claude import ClaudeReply, ask_claude
from quizkit.files import write_atomically
from quizkit.models import Card

BLOCK_SPEC = BlockSpec(
    name="answer_writer",
    kind="agent",
    goal="Write, for each card, the English answers a learner might type, saved to data/generated/answers.jsonl",
    inputs=[
        "`cards` (`list[Card]`)",
        "`limit` (`int | None`)",
        "`dry_run` (`bool`)",
        "`chunk_size` (`int`, default 40)",
        "`ask` (function)",
    ],
    outputs=[
        "data/generated/answers.jsonl",
        "data/generated/answer_writer_log.jsonl",
        "validate_answers(lines, cards) -> list[str]",
        "load_answers(path, cards) -> dict[str, list[str]]",
        "A summary on screen",
    ],
)

ROOT = Path(__file__).resolve().parents[4]
ANSWERS_FILE = ROOT / "data" / "generated" / "answers.jsonl"
LOG_FILE = ROOT / "data" / "generated" / "answer_writer_log.jsonl"
MODEL = "sonnet"
MAX_ANSWERS = 10
MAX_CHARS = 40
TYPEABLE = re.compile(r"(?=.*[A-Za-z0-9])[A-Za-z0-9' .-]+")  # needs a letter/digit

PROMPT_VERSION = "1"
SYSTEM = (
    "You write answer keys for a Mandarin vocabulary quiz. "
    "Reply with JSON only, no other text."
)
INSTRUCTIONS = """\
A learner sees a Chinese word from the HSK 3.0 syllabus (band 1 = easiest) and types
its meaning in English. For each word below, list the English answers that should be
marked RIGHT.

Rules:
- Cover the word's HSK meaning: the common, everyday sense a learner at that band
  is taught. Skip surnames, place names, rare, literary or slang senses. The
  dictionary meanings are a hint and may include senses that are not the HSK one.
- Include common synonyms and natural ways to say it (爸爸: father, dad, papa).
- Most likely answer first. 1 to 10 answers per word.
- Each answer: 1-40 characters, only English letters, digits, spaces, apostrophes,
  full stops and hyphens. No brackets, notes, slashes, other punctuation or Chinese.
- Verbs without "to" (love, not to love): the quiz ignores a leading "to".
- Grammar words with no English equivalent (particles, measure words): give the
  short labels a learner might type, e.g. "question particle".

Reply with exactly this JSON, one entry per word, every id exactly once:
{"cards": [{"id": "<id>", "answers": ["...", "..."]}]}

Words (JSON, one per line):
"""


class AnswerLine(BaseModel):
    """One line of answers.jsonl."""

    model_config = ConfigDict(frozen=True)

    id: str
    hanzi: str
    answers: list[str]
    model: str
    prompt_version: str


class AnswerRun(BaseModel):
    """What a run did."""

    written: int = 0
    skipped: int = 0
    failed: list[str] = []
    input_tokens: int = 0
    output_tokens: int = 0


class AnswerFileError(ValueError):
    """answers.jsonl can't be opened or read, or (load_answers) isn't a good answer
    list for the cards asked about (e.g. after a hand edit)."""


class _ReplyCard(BaseModel):
    id: object = None  # all checked per card, so one bad card fails alone
    answers: object = None


class _Reply(BaseModel):
    cards: list[_ReplyCard]


def build_prompt(cards: list[Card]) -> str:
    rows = [
        json.dumps(
            {
                "id": c.id,
                "hanzi": c.fields.get("hanzi", c.id),
                "pinyin": c.fields.get("pinyin", ""),
                "part_of_speech": c.fields.get("pos", ""),
                "band": c.level,
                "dictionary": c.answers,
            },
            ensure_ascii=False,
        )
        for c in cards
    ]
    return INSTRUCTIONS + "\n".join(rows) + "\n"


def _same_key(answer: str) -> str:
    """How the grader compares answers: "To Love" and "love" are the same answer."""
    return clean(answer, GradeSettings()) or answer.strip().lower()


def _without_repeats(answers: list[str]) -> list[str]:
    """Trimmed, with later repeats (as the grader sees them) removed: they do no harm."""
    kept: list[str] = []
    seen: set[str] = set()
    for answer in (a.strip() for a in answers):
        if _same_key(answer) not in seen:
            seen.add(_same_key(answer))
            kept.append(answer)
    return kept


def _line_problems(line: AnswerLine) -> list[str]:
    answers = line.answers if isinstance(line.answers, list) else []
    problems = []
    if not 1 <= len(answers) <= MAX_ANSWERS:
        problems.append(f"{line.id}: needs 1-{MAX_ANSWERS} answers, has {len(answers)}")
    seen: set[str] = set()
    for answer in answers:
        text = answer if isinstance(answer, str) else ""
        if not 1 <= len(text.strip()) or len(text) > MAX_CHARS:
            problems.append(f"{line.id}: answer {answer!r} must be 1-{MAX_CHARS} chars")
        elif not TYPEABLE.fullmatch(text):
            problems.append(
                f"{line.id}: answer {answer!r} may only use letters, digits, spaces, ' . and -"
            )
        if not isinstance(answer, str):
            continue
        key = _same_key(text)
        if key in seen:
            problems.append(f"{line.id}: answer {answer!r} is listed twice")
        seen.add(key)
    return problems


def validate_answers(
    lines: list[AnswerLine], cards: list[Card], require_all: bool = False
) -> list[str]:
    """The problems found (empty list = good)."""
    known = {c.id for c in cards}
    problems: list[str] = []
    counted: set[str] = set()
    for line in lines:
        if line.id not in known:
            problems.append(f"{line.id}: not a card in cards.jsonl")
        if line.id in counted:
            problems.append(f"{line.id}: appears more than once")
        counted.add(line.id)
        problems += _line_problems(line)
    if require_all:
        problems += [f"{c.id}: missing" for c in cards if c.id not in counted]
    return problems


def parse_reply(text: str) -> _Reply:
    """Claude's JSON reply (a ```json fence around it is fine). Raises ValueError."""
    body = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", body, flags=re.DOTALL)
    if fence:
        body = fence.group(1)
    try:
        return _Reply.model_validate_json(body)
    except ValidationError as err:
        raise ValueError(f"reply is not the JSON asked for: {err}") from err


def _read_lines(path: Path) -> list[tuple[int, AnswerLine]]:
    """Every line of an answers file with its line number (blank lines skipped).

    Raises AnswerFileError if the file can't be opened or a line can't be read.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:  # missing, a folder, not UTF-8...
        raise AnswerFileError(f"can't open {path}: {err}") from err
    lines = []
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            lines.append((number, AnswerLine.model_validate_json(raw)))
        except ValidationError as err:
            raise AnswerFileError(
                f"{path.name} line {number} can't be read; fix or delete it: {err}"
            ) from err
    return lines


def load_answers(path: Path, cards: list[Card]) -> dict[str, list[str]]:
    """Each card's answers by id, only if the file is good for these cards (see SPEC).

    Same rules as the writer, so the two always agree on a good file: repeated answers
    are tidied away (they do no harm), then the checker runs. Lines for other ids are
    ignored. Raises AnswerFileError listing the problems.
    """
    known = {c.id for c in cards}
    lines = [
        line.model_copy(update={"answers": _without_repeats(line.answers)})
        for _, line in _read_lines(path)
        if line.id in known
    ]
    problems = validate_answers(lines, cards, require_all=True)
    if problems:
        more = f"; and {len(problems) - 5} more" if len(problems) > 5 else ""
        raise AnswerFileError(
            f"{path.name} isn't a good answer list: " + "; ".join(problems[:5]) + more
        )
    return {line.id: line.answers for line in lines}


def _load_existing(
    out: Path, known: set[str]
) -> tuple[dict[str, AnswerLine], dict[str, AnswerLine], bool]:
    """(done, saved, changed): the current good lines; every card's saved line to keep
    until it's replaced; whether the file needs rewriting.

    The file never shrinks (the quiz needs every card): only a line for a card that's
    gone is dropped. A line from an older PROMPT_VERSION, failing the checker, or
    listed twice is asked again but stays saved meanwhile (if twice: the first copy
    that passes the checker, else the first copy). Lines that pass are tidied.
    """
    if not out.exists():
        return {}, {}, False
    done: dict[str, AnswerLine] = {}
    saved: dict[str, AnswerLine] = {}
    usable: set[str] = set()  # ids whose saved line passes the checker
    changed = False
    for _, line in _read_lines(out):
        if line.id not in known:
            print(f"Warning: dropped {line.id!r} from {out.name} (no longer a card)")
            changed = True
            continue
        tidy = line.model_copy(update={"answers": _without_repeats(line.answers)})
        problems = _line_problems(tidy)
        twice = line.id in saved
        changed |= twice  # only one copy is written back
        if not problems and line.id not in usable:  # the first copy that passes wins
            changed |= twice or tidy.answers != line.answers
            saved[line.id] = tidy
            usable.add(line.id)
        elif not twice:
            saved[line.id] = line  # kept as it is until it's replaced
        if line.prompt_version != PROMPT_VERSION or problems or twice:
            why = "; ".join(problems) or (
                "listed more than once" if twice else "older prompt version"
            )
            print(f"Will redo {line.id!r}: {why}")
            done.pop(line.id, None)
            continue
        done[line.id] = tidy  # first copy, current version, passes the checker
    return done, saved, changed


def _save(
    out: Path,
    cards: list[Card],
    done: dict[str, AnswerLine],
    saved: dict[str, AnswerLine],
) -> None:
    """Write every card's newest line: done this run or good, else the old saved one."""
    rows = [
        (done.get(c.id) or saved[c.id]).model_dump()
        for c in cards
        if c.id in done or c.id in saved
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    write_atomically(out, data.encode("utf-8"))


def _log(log: Path, reply: ClaudeReply, n_cards: int) -> None:
    entry = {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": reply.model,
        "prompt_version": PROMPT_VERSION,
        "cards": n_cards,
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
        "cost_usd": reply.cost_usd,
    }
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def write_answers(
    cards: list[Card],
    limit: int | None = None,
    dry_run: bool = False,
    chunk_size: int = 40,
    ask: Callable[[str], ClaudeReply] = lambda prompt: ask_claude(
        prompt, model=MODEL, system=SYSTEM
    ),
    out: Path = ANSWERS_FILE,
    log: Path = LOG_FILE,
) -> AnswerRun:
    """Ask Claude for the answers of every card not yet in `out`; save after each chunk.

    A ClaudeError stops the run: what's done is already saved, then it goes up.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    if limit is not None and limit < 0:
        raise ValueError("limit can't be negative")
    done, saved, changed = _load_existing(out, {c.id for c in cards})
    if changed and not dry_run:  # tidied / dropped lines are written back at once
        _save(out, cards, done, saved)
    todo = [c for c in cards if c.id not in done]
    if limit is not None:
        todo = todo[:limit]
    run = AnswerRun(skipped=sum(c.id in done for c in cards))
    chunks = [todo[i : i + chunk_size] for i in range(0, len(todo), chunk_size)]

    if dry_run:
        for n, chunk in enumerate(chunks, 1):
            print(f"--- call {n} of {len(chunks)} ({len(chunk)} cards) ---")
            print(build_prompt(chunk))
        print(f"Dry run: {len(todo)} cards in {len(chunks)} calls; nothing sent.")
        return run

    try:
        for chunk in chunks:
            _do_chunk(chunk, ask, cards, done, saved, run, out, log)
    finally:  # also after a ClaudeError, so the summary is never lost
        _print_summary(run)
    return run


def _do_chunk(chunk, ask, cards, done, saved, run, out, log) -> None:
    reply = ask(build_prompt(chunk))  # ClaudeError goes up: earlier chunks saved
    _log(log, reply, len(chunk))
    run.input_tokens += reply.input_tokens
    run.output_tokens += reply.output_tokens
    try:
        parsed = {
            c.id: c.answers
            for c in parse_reply(reply.text).cards
            if isinstance(c.id, str)
        }
    except ValueError as err:
        print(f"Chunk failed ({len(chunk)} cards): {err}")
        run.failed += [c.id for c in chunk]
        return
    for card in chunk:
        given = parsed.get(card.id)
        if not (isinstance(given, list) and all(isinstance(a, str) for a in given)):
            if card.id in parsed:
                print(f"Not saved: {card.id}: answers must be a list of text")
            run.failed.append(card.id)
            continue
        line = AnswerLine(
            id=card.id,
            hanzi=card.fields.get("hanzi", card.id),
            answers=_without_repeats(given),
            model=reply.model,
            prompt_version=PROMPT_VERSION,
        )
        problems = _line_problems(line)
        if problems:
            print("Not saved: " + "; ".join(problems))
            run.failed.append(card.id)
            continue
        done[card.id] = line
        run.written += 1
    _save(out, cards, done, saved)


def _print_summary(run: AnswerRun) -> None:
    print(
        f"{run.written} written, {run.skipped} skipped, {len(run.failed)} failed"
        f" · {run.input_tokens + run.output_tokens:,} tokens"
    )
    if run.failed:
        print("Failed (re-run to retry): " + ", ".join(run.failed))
