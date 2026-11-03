"""sentence_writer: Ask Claude for 1-2 short example sentences per word, keep only the
ones the sentence checker passes (retrying failures with its reasons), add pinyin by
script, and save them to data/generated/sentences.jsonl.

See SPEC.md in this folder (ADR 0003, ADR 0008, ADR 0009).
Run by hand: uv run python -m hsk_trainer.blocks.sentence_writer --limit 20 [--dry-run]
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError
from pypinyin import Style, lazy_pinyin

from hsk_trainer.blocks.sentence_validator import (
    Vocab,
    _is_hanzi,  # the checker's own test, so both read text alike
    check_sentence,
)
from quizkit.blocks.base import BlockSpec
from quizkit.claude import ClaudeReply, ask_claude
from quizkit.files import write_atomically
from quizkit.models import Card

BLOCK_SPEC = BlockSpec(
    name="sentence_writer",
    kind="agent",
    goal="Ask Claude for 1-2 short example sentences per word, keep only the ones the sentence checker passes (retrying failures with its reasons), add pinyin by script, and save them to data/generated/sentences.jsonl.",
    inputs=["cards", "limit", "dry_run", "chunk_size", "retries", "ask"],
    outputs=["sentences.jsonl", "sentence_writer_log.jsonl", "SentenceRun"],
)

ROOT = Path(__file__).resolve().parents[4]
SENTENCES_FILE = ROOT / "data" / "generated" / "sentences.jsonl"
LOG_FILE = ROOT / "data" / "generated" / "sentence_writer_log.jsonl"
MODEL = "sonnet"
MAX_SENTENCES = 2
MAX_ENGLISH = 120
ENGLISH = re.compile(r"(?=.*[A-Za-z])[A-Za-z0-9 .,!?'\"():;/%&-]+")  # needs a letter
# Typographic marks Claude often uses, made plain before the check (and saved plain).
PLAIN = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
    }
)

PROMPT_VERSION = "1"
SYSTEM = (
    "You write example sentences for a Mandarin vocabulary quiz. "
    "Reply with JSON only, no other text."
)
INSTRUCTIONS = """\
A learner studies Chinese words from the HSK 3.0 syllabus (band 1 = easiest). For each
word below, write 2 short, natural example sentences a learner at band {band} can read.

Rules for every sentence:
- It contains the word exactly as written, used as that word (not inside a longer word).
- Every other word comes from the allowed word list below. No other words.
- Only Chinese characters and Chinese punctuation (，。？！、：；“”). No names, no
  digits, no Latin letters, no spaces.
- 3 to 20 Chinese characters.
- Give a plain English translation: 1-120 characters, English letters, digits, spaces
  and normal punctuation only.

Allowed words (band 1 to {band}):
{allowed}

Reply with exactly this JSON, one entry per word, every id exactly once:
{{"cards": [{{"id": "<id>", "sentences": [{{"hanzi": "...", "english": "..."}}]}}]}}

Words (JSON, one per line):
"""
RETRY_NOTE = """\
Your earlier sentences for these words were rejected by a checker. Its reasons are
listed with each word. Write 2 new sentences per word that avoid those problems.

"""
REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "sentences": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "hanzi": {"type": "string"},
                                "english": {"type": "string"},
                            },
                            "required": ["hanzi", "english"],
                        },
                    },
                },
                "required": ["id", "sentences"],
            },
        }
    },
    "required": ["cards"],
}


class Sentence(BaseModel):
    """One example sentence, as saved."""

    model_config = ConfigDict(frozen=True)

    hanzi: str
    pinyin: str
    english: str


class SentenceLine(BaseModel):
    """One line of sentences.jsonl."""

    model_config = ConfigDict(frozen=True)

    id: str
    hanzi: str
    sentences: list[Sentence]
    model: str
    prompt_version: str


class SentenceRun(BaseModel):
    """What a run did."""

    written: int = 0
    skipped: int = 0
    failed: list[str] = []
    input_tokens: int = 0
    output_tokens: int = 0


class SentenceFileError(ValueError):
    """sentences.jsonl can't be opened, or one of its lines can't be read."""


class _ReplyCard(BaseModel):
    id: object = None  # all checked per word, so one bad word fails alone
    sentences: object = None


class _Reply(BaseModel):
    cards: list[object]  # each item checked on its own, so one bad item fails alone


# -- pinyin (by script, ADR 0008) ----------------------------------------------------


def _fewest_pieces(text: str, words: set[str]) -> list[str]:
    """Read `text` as the fewest pieces (HSK words or single characters)."""
    longest = max((len(w) for w in words), default=1)
    n = len(text)
    best: list[list[str] | None] = [None] * (n + 1)
    best[0] = []
    for i in range(n):
        here = best[i]
        if here is None:
            continue
        if not _is_hanzi(text[i]) and not any(text.startswith(w, i) for w in words):
            if best[i + 1] is None or len(here) < len(best[i + 1]):
                best[i + 1] = here  # punctuation: no piece
            continue
        for end in range(i + 1, min(n, i + longest) + 1):
            piece = text[i:end]
            better = best[end] is None or len(here) + 1 < len(best[end])
            if (end == i + 1 or piece in words) and better:
                best[end] = [*here, piece]
    return best[n] or []


def sentence_pinyin(
    sentence: str, cards: list[Card], words: tuple[str, ...] | None = None
) -> str:
    """The pinyin line for `sentence`: dictionary pinyin for HSK words with one
    reading, pypinyin for everything else; punctuation kept as written.

    `words` is the checker's reading (SentenceCheck.words); without it, the sentence
    is read as the fewest HSK words.
    """
    dictionary = {
        c.fields["hanzi"]: c.fields["pinyin"]
        for c in cards
        if str(c.fields.get("readings", "1")) == "1" and c.fields.get("pinyin")
    }
    text = sentence.strip()
    if words is None:
        words = tuple(_fewest_pieces(text, {c.fields["hanzi"] for c in cards}))
    # pypinyin reads the whole sentence once, so it sees each character's context;
    # `errors` keeps every other character as its own item: one item per character.
    guess = lazy_pinyin(text, style=Style.TONE, errors=lambda other: list(other))
    tokens: list[str] = []
    i = k = 0
    while i < len(text):
        if k < len(words) and text.startswith(words[k], i):
            word = words[k]
            k += 1
            if word in dictionary:
                tokens.extend(dictionary[word].split())
            else:
                tokens.extend(guess[i : i + len(word)])
            i += len(word)
        else:
            tokens.append(guess[i])  # punctuation, kept as written
            i += 1

    out = ""
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        syllable = any(ch.isalpha() for ch in token)
        previous = bool(out) and out[-1].isalpha()
        out += (" " if syllable and previous else "") + token
    return out


# -- checking ------------------------------------------------------------------------


def _english_ok(text: str) -> bool:
    return 1 <= len(text) <= MAX_ENGLISH and bool(ENGLISH.fullmatch(text))


ENGLISH_REASON = (
    f"the English must be 1-{MAX_ENGLISH} characters: English letters, digits, "
    "spaces and normal punctuation"
)


def _sentence_problems(hanzi: str, english: str, word: str, vocab: Vocab) -> list[str]:
    check = check_sentence(hanzi, word, vocab)
    problems = list(check.reasons)
    if not _english_ok(english):
        problems.append(ENGLISH_REASON)
    return problems


def _line_problems(line: SentenceLine, word: str, vocab: Vocab) -> list[str]:
    if not 1 <= len(line.sentences) <= MAX_SENTENCES:
        return [f"needs 1-{MAX_SENTENCES} sentences, has {len(line.sentences)}"]
    problems: list[str] = []
    if len({s.hanzi for s in line.sentences}) < len(line.sentences):
        problems.append("the same sentence is listed twice")
    for s in line.sentences:
        problems += [
            f"{s.hanzi}: {p}"
            for p in _sentence_problems(s.hanzi, s.english, word, vocab)
        ]
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


def _pairs(given: object) -> list[tuple[str, str]] | None:
    """The (hanzi, english) pairs Claude gave for one word, or None if malformed."""
    if not isinstance(given, list):
        return None
    pairs = []
    for s in given:
        if not isinstance(s, dict):
            continue
        hanzi, english = s.get("hanzi"), s.get("english")
        if isinstance(hanzi, str) and isinstance(english, str):
            pairs.append((hanzi.strip(), english.translate(PLAIN).strip()))
    return pairs


# -- prompts -------------------------------------------------------------------------


def _allowed(cards: list[Card], band: int) -> str:
    return "、".join(c.fields["hanzi"] for c in cards if c.level <= band)


def _row(card: Card, **extra) -> str:
    return json.dumps(
        {
            "id": card.id,
            "hanzi": card.fields.get("hanzi", card.id),
            "pinyin": card.fields.get("pinyin", ""),
            "meanings": card.answers,
            **extra,
        },
        ensure_ascii=False,
    )


def build_prompt(
    chunk: list[Card],
    cards: list[Card],
    band: int,
    rejected: dict[str, list[tuple[str, list[str]]]] | None = None,
) -> str:
    """The prompt for one call: one band. With `rejected`, it's a retry and each word
    carries its rejected sentences and the checker's reasons."""
    head = INSTRUCTIONS.format(band=band, allowed=_allowed(cards, band))
    if rejected is None:
        return head + "\n".join(_row(c) for c in chunk) + "\n"
    rows = []
    for c in chunk:
        tries = rejected.get(c.id) or []
        shown = [{"sentence": h, "reasons": r} for h, r in tries] or [
            {"sentence": None, "reasons": ["no usable sentences came back"]}
        ]
        rows.append(_row(c, rejected=shown))
    return RETRY_NOTE + head + "\n".join(rows) + "\n"


# -- the file ------------------------------------------------------------------------


def _read_lines(path: Path) -> list[SentenceLine]:
    """Every line of a sentences file (blank lines skipped). Raises SentenceFileError."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise SentenceFileError(f"can't open {path}: {err}") from err
    lines = []
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            lines.append(SentenceLine.model_validate_json(raw))
        except ValidationError as err:
            raise SentenceFileError(
                f"{path.name} line {number} can't be read; fix or delete it: {err}"
            ) from err
    return lines


def _fresh_pinyin(line: SentenceLine, cards: list[Card], vocab: Vocab) -> SentenceLine:
    """The line with its pinyin made again by script (free, and always the same)."""
    sentences = [
        s.model_copy(
            update={
                "pinyin": sentence_pinyin(
                    s.hanzi, cards, check_sentence(s.hanzi, line.hanzi, vocab).words
                )
            }
        )
        for s in line.sentences
    ]
    return line.model_copy(update={"sentences": sentences})


def _load_existing(
    out: Path, cards: list[Card], vocab: Vocab
) -> tuple[dict[str, SentenceLine], dict[str, SentenceLine], bool]:
    """(done, saved, changed): current passing lines; every saved line to keep until
    it's replaced; whether the file needs rewriting (a line dropped, listed twice, or
    its pinyin out of date).

    A word listed twice keeps its first copy that passes the checker (else the first).
    A current, passing line gets its pinyin made again, so a hand edit can't stick.
    """
    if not out.exists():
        return {}, {}, False
    by_id = {c.id: c for c in cards}
    done: dict[str, SentenceLine] = {}
    saved: dict[str, SentenceLine] = {}
    usable: set[str] = set()  # ids whose kept line passes the checker
    changed = False
    for line in _read_lines(out):
        if line.id not in by_id:
            print(f"Warning: dropped {line.id!r} from {out.name} (no longer a card)")
            changed = True
            continue
        hanzi = by_id[line.id].fields["hanzi"]
        changed |= line.hanzi != hanzi
        line = line.model_copy(update={"hanzi": hanzi})
        problems = _line_problems(line, line.hanzi, vocab)
        current = line.prompt_version == PROMPT_VERSION
        if line.id in saved:
            print(f"Warning: {line.id!r} is listed twice in {out.name}; kept one copy")
            changed = True
            better = line.id not in done and current
            if problems or (line.id in usable and not better):
                continue
        if not problems:
            usable.add(line.id)
            if current:
                fresh = _fresh_pinyin(line, cards, vocab)
                changed |= fresh != line
                line = fresh
        saved[line.id] = line
        if current and not problems:
            done[line.id] = line
        else:
            why = "; ".join(problems) or "older prompt version"
            print(f"Will redo {line.id!r}: {why}")
    return done, saved, changed


def _save(
    out: Path,
    cards: list[Card],
    done: dict[str, SentenceLine],
    saved: dict[str, SentenceLine],
) -> None:
    """Write every word's newest line: done this run or good, else the old saved one."""
    rows = [
        (done.get(c.id) or saved[c.id]).model_dump()
        for c in cards
        if c.id in done or c.id in saved
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    write_atomically(out, data.encode("utf-8"))


def _log(log: Path, reply: ClaudeReply, n_cards: int, retry: int) -> None:
    entry = {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": reply.model,
        "prompt_version": PROMPT_VERSION,
        "cards": n_cards,
        "retry": retry,
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
        "cost_usd": reply.cost_usd,
    }
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# -- the run -------------------------------------------------------------------------


class _Job:
    """Everything one run shares, so the steps below stay small."""

    def __init__(self, cards, vocab, ask, out, log, done, saved, run) -> None:
        self.cards = cards
        self.vocab = vocab
        self.ask = ask
        self.out = out
        self.log = log
        self.done = done
        self.saved = saved
        self.run = run

    def call(
        self,
        chunk: list[Card],
        band: int,
        retry: int,
        rejected: dict[str, list[tuple[str, list[str]]]] | None = None,
    ) -> dict[str, list[tuple[str, list[str]]]]:
        """One Claude call. Saves the words that got a passing sentence; returns the
        others with their rejected sentences and reasons."""
        prompt = build_prompt(chunk, self.cards, band, rejected)
        reply = self.ask(prompt, model=MODEL, system=SYSTEM, json_schema=REPLY_SCHEMA)
        _log(self.log, reply, len(chunk), retry)
        self.run.input_tokens += reply.input_tokens
        self.run.output_tokens += reply.output_tokens
        try:
            items = parse_reply(reply.text).cards
        except ValueError as err:
            print(f"Call failed ({len(chunk)} words): {err}")
            return {c.id: [] for c in chunk}
        parsed: dict[str, object] = {}
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                parsed.setdefault(item["id"], item.get("sentences"))  # first one wins
        failed: dict[str, list[tuple[str, list[str]]]] = {}
        for card in chunk:
            word = card.fields["hanzi"]
            pairs = _pairs(parsed.get(card.id)) or []
            good: list[Sentence] = []
            bad: list[tuple[str, list[str]]] = []
            for hanzi, english in pairs:
                if len(good) == MAX_SENTENCES:
                    break
                if any(g.hanzi == hanzi for g in good) or any(
                    b[0] == hanzi for b in bad
                ):
                    continue  # the same sentence twice counts once
                problems = _sentence_problems(hanzi, english, word, self.vocab)
                if problems:
                    bad.append((hanzi, problems))
                    continue
                reading = check_sentence(hanzi, word, self.vocab).words
                pinyin = sentence_pinyin(hanzi, self.cards, reading)
                good.append(Sentence(hanzi=hanzi, pinyin=pinyin, english=english))
            if not good:
                failed[card.id] = bad
                continue
            self.done[card.id] = SentenceLine(
                id=card.id,
                hanzi=word,
                sentences=good,
                model=reply.model,
                prompt_version=PROMPT_VERSION,
            )
            self.run.written += 1
        _save(self.out, self.cards, self.done, self.saved)
        return failed

    def band(self, band: int, todo: list[Card], chunk_size: int, retries: int) -> None:
        """First tries for one band, then up to `retries` rounds for the words left."""
        failed: dict[str, list[tuple[str, list[str]]]] = {}
        ever: set[str] = set()  # failed at least once (and maybe fixed later)
        try:
            for chunk in _chunks(todo, chunk_size):
                failed |= self.call(chunk, band, 0)
                ever |= set(failed)
            for retry in range(1, retries + 1):
                left = [c for c in todo if c.id in failed]
                if not left:
                    break
                again: dict[str, list[tuple[str, list[str]]]] = {}
                for chunk in _chunks(left, chunk_size):
                    again |= self.call(chunk, band, retry, failed)
                    ever |= set(again)
                failed = again
        finally:  # also after a ClaudeError, so the summary lists them
            self.run.failed += [
                c.id for c in todo if c.id in ever and c.id not in self.done
            ]


def _chunks(cards: list[Card], size: int) -> list[list[Card]]:
    return [cards[i : i + size] for i in range(0, len(cards), size)]


def write_sentences(
    cards: list[Card],
    limit: int | None = None,
    dry_run: bool = False,
    chunk_size: int = 20,
    retries: int = 2,
    ask: Callable[..., ClaudeReply] = ask_claude,
    out: Path = SENTENCES_FILE,
    log: Path = LOG_FILE,
) -> SentenceRun:
    """Ask Claude for sentences for every word not yet done in `out`; save after each
    call. A ClaudeError stops the run: what's done is already saved, then it goes up.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    if limit is not None and limit < 0:
        raise ValueError("limit can't be negative")
    if retries < 0:
        raise ValueError("retries can't be negative")
    if not cards:
        raise ValueError("no cards")
    vocab = Vocab(cards)
    done, saved, changed = _load_existing(out, cards, vocab)
    if changed and not dry_run:  # dropped / repeated lines are written back at once
        _save(out, cards, done, saved)
    todo = [c for c in cards if c.id not in done]
    if limit is not None:
        todo = todo[:limit]
    run = SentenceRun(skipped=sum(c.id in done for c in cards))
    bands = sorted({c.level for c in todo})

    if dry_run:
        calls = sum(
            len(_chunks([c for c in todo if c.level == b], chunk_size)) for b in bands
        )
        if todo:
            first = [c for c in todo if c.level == bands[0]][:chunk_size]
            print("--- first call ---")
            print(build_prompt(first, cards, bands[0]))
        print(
            f"Dry run: {len(todo)} words in {calls} calls (before retries); nothing sent."
        )
        return run

    job = _Job(cards, vocab, ask, out, log, done, saved, run)
    try:
        for band in bands:
            job.band(band, [c for c in todo if c.level == band], chunk_size, retries)
    finally:  # also after a ClaudeError, so the summary is never lost
        _print_summary(run)
    return run


def _print_summary(run: SentenceRun) -> None:
    print(
        f"{run.written} written, {run.skipped} skipped, {len(run.failed)} failed"
        f" · {run.input_tokens + run.output_tokens:,} tokens"
    )
    if run.failed:
        print("Failed (re-run to retry): " + ", ".join(run.failed))
