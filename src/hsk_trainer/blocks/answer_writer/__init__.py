"""answer_writer: Write, for each card, the English answers a learner might type,
saved to data/generated/answers.jsonl

See SPEC.md in this folder (ADR 0003, ADR 0005).
Run by hand: uv run python -m hsk_trainer.blocks.answer_writer --limit 20 [--dry-run]
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from quizkit.blocks.base import BlockSpec
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
    """answers.jsonl has a line that can't be read (e.g. after a hand edit)."""


class _ReplyCard(BaseModel):
    id: object  # both checked per card, so one bad card fails alone
    answers: object


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


def _without_repeats(answers: list[str]) -> list[str]:
    """Trimmed, with later repeats (ignoring case) removed: a repeat does no harm."""
    kept: list[str] = []
    for answer in (a.strip() for a in answers):
        if answer.lower() not in {k.lower() for k in kept}:
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
        key = text.strip().lower()
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


def _load_existing(out: Path, known: set[str]) -> dict[str, AnswerLine]:
    if not out.exists():
        return {}
    done: dict[str, AnswerLine] = {}
    for number, raw in enumerate(out.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            line = AnswerLine.model_validate_json(raw)
        except ValidationError as err:
            raise AnswerFileError(
                f"{out.name} line {number} can't be read; fix or delete it: {err}"
            ) from err
        if line.id in known:
            done[line.id] = line
        else:
            print(f"Warning: dropped {line.id!r} from {out.name} (no longer a card)")
    return done


def _save(out: Path, cards: list[Card], done: dict[str, AnswerLine]) -> None:
    rows = [done[c.id].model_dump_json() for c in cards if c.id in done]
    out.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(json.loads(r), ensure_ascii=False) + "\n" for r in rows)
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
    done = _load_existing(out, {c.id for c in cards})
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

    for chunk in chunks:
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
            continue
        for card in chunk:
            given = parsed.get(card.id)
            if given is None or not (
                isinstance(given, list) and all(isinstance(a, str) for a in given)
            ):
                if given is not None:
                    print(f"Not saved: {card.id}: answers must all be text")
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
        _save(out, cards, done)

    print(
        f"{run.written} written, {run.skipped} skipped, {len(run.failed)} failed"
        f" · {run.input_tokens + run.output_tokens:,} tokens"
    )
    if run.failed:
        print("Failed (re-run to retry): " + ", ".join(run.failed))
    return run
