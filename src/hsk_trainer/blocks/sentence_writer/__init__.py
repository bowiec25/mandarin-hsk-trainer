"""sentence_writer: Ask Claude for 1-2 short example sentences per word, with pinyin
and English; keep only the ones the scripts pass (retrying failures with the reasons),
and save them to data/generated/sentences.jsonl.

See SPEC.md in this folder (ADR 0003, ADR 0008, ADR 0009, ADR 0010).
Run by hand: uv run python -m hsk_trainer.blocks.sentence_writer --limit 20 [--dry-run]
"""

import json
import re
import threading
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError
from pypinyin import Style
from pypinyin import pinyin as all_readings

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
    goal="Ask Claude for 1-2 short example sentences per word, with pinyin and English; keep only the ones the scripts pass (retrying failures with the reasons), and save them to data/generated/sentences.jsonl.",
    inputs=[
        "cards",
        "limit",
        "dry_run",
        "chunk_size",
        "retries",
        "ask",
        "removed",
        "card",
        "vocab",
        "timeout",
    ],
    outputs=[
        "sentences.jsonl",
        "sentence_writer_log.jsonl",
        "live_sentence_log.jsonl",
        "SentenceRun",
        "WrittenSentences",
    ],
)

ROOT = Path(__file__).resolve().parents[4]
SENTENCES_FILE = ROOT / "data" / "generated" / "sentences.jsonl"
LOG_FILE = ROOT / "data" / "generated" / "sentence_writer_log.jsonl"
# Calls made during play (write_one): gitignored, so playing never changes the repo.
LIVE_LOG_FILE = ROOT / "data" / "live_sentence_log.jsonl"
# Sentences an audit removed (ADR 0015): committed, never saved or shown again.
REMOVED_FILE = ROOT / "data" / "generated" / "sentences_removed.json"
_LOG_LOCK = threading.Lock()  # write_one runs on quiz background threads
MODEL = "sonnet"
MAX_SENTENCES = 2  # asked for, and kept, per word per call
MAX_SAVED = 10  # most sentences one word may have saved (the bank's cap, ADR 0011)
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

PROMPT_VERSION = "2"
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
- Give its pinyin: tone marks (never tone numbers), one syllable per Chinese
  character, separated by spaces; 儿 after a word is its own syllable r (nǎ r).
  Write each syllable as a dictionary does: its full tone (no tone changes for 一 or
  不, and 个 is gè), and no mark only where the dictionary writes a neutral tone
  (bà ba, péng you). Pick the reading that fits the sentence.
- Give a plain English translation: 1-120 characters, English letters, digits, spaces
  and normal punctuation only.

Allowed words (band 1 to {band}):
{allowed}

Reply with exactly this JSON, one entry per word, every id exactly once:
{{"cards": [{{"id": "<id>", "sentences": [{{"hanzi": "...", "pinyin": "...", "english": "..."}}]}}]}}

Words (JSON, one per line):
"""
RETRY_NOTE = """\
Your earlier sentences for these words were rejected by a checker (the words, the
pinyin or the English). Its reasons are listed with each word. Write 2 new sentences per word that avoid those problems.

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
                                "pinyin": {"type": "string"},
                                "english": {"type": "string"},
                            },
                            "required": ["hanzi", "pinyin", "english"],
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


class RemovedListError(SentenceFileError):
    """The removed list can't be read (a SentenceFileError, so old callers still
    catch it; new ones can name the right file)."""


def read_removed(path: Path) -> dict[str, list[str]]:
    """The removed list, or {} if it's missing. Committed data, so a broken one is
    loud (SentenceFileError naming the file), like the bank itself."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("not an object of word -> list of sentences")
        for word, sentences in data.items():
            if not isinstance(sentences, list) or not all(
                isinstance(s, str) for s in sentences
            ):
                raise TypeError(f"{word!r} is not a list of sentences (text)")
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as err:
        raise RemovedListError(f"{path.name}: {err}") from err
    return data


class _ReplyCard(BaseModel):
    id: object = None  # all checked per word, so one bad word fails alone
    sentences: object = None


class _Reply(BaseModel):
    cards: list[object]  # each item checked on its own, so one bad item fails alone


# -- pinyin: Claude writes it, a script checks it (ADR 0010) ------------------------

# Pinyin letters: a-z, the tone-marked vowels, ü, and combining tone marks.
_SYLLABLE = re.compile(
    r"[A-Za-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüÜêÊếềẾỀńňǹḿŃŇǸḾĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙǕǗǙǛ\u0300-\u036f]+"
)


def _syllables(text: str) -> list[str]:
    """The runs of letters (with tone marks) in a pinyin text; the rest is ignored."""
    return _SYLLABLE.findall(unicodedata.normalize("NFC", text))


def _key(syllable: str) -> str:
    """How syllables are compared: no case, `v` read as `ü`."""
    plain = unicodedata.normalize("NFC", syllable).lower().replace("v", "ü")
    return unicodedata.normalize("NFC", plain)


def _neutral(syllable: str) -> str:
    """The syllable with its tone mark left off (ü keeps its dots)."""
    parts = unicodedata.normalize("NFD", _key(syllable))
    kept = "".join(c for c in parts if not unicodedata.combining(c) or c == "\u0308")
    return unicodedata.normalize("NFC", kept)


def _fits(given: str, reading: str, ch: str) -> bool:
    """`given` is `reading`, or, where the reading is neutral, a full tone that is a
    real reading of the character `ch` (duì bù qǐ for duì bu qǐ; not 了 lè). Leaving
    a tone mark off is never fine: the dictionary already writes the real neutral
    tones (bà ba)."""
    mine, theirs = _key(given), _key(reading)
    if mine == theirs:
        return True
    if theirs != _neutral(theirs) or _neutral(mine) != theirs:
        return False
    return mine in {_key(r) for r in _char_readings(ch)}


def _char_readings(ch: str) -> list[str]:
    """Every reading pypinyin knows for one character (empty if none)."""
    found = all_readings(ch, style=Style.TONE, heteronym=True)[0]
    readings = [r for r in found if r != ch]
    return [*readings, "r"] if ch == "儿" else readings  # 儿 after a word: nǎ r


def pinyin_problems(
    sentence: str, pinyin: str, words: tuple[str, ...], cards: list[Card]
) -> list[str]:
    """What's wrong with Claude's pinyin for `sentence` (empty list = good).

    `words` is the checker's reading (SentenceCheck.words). An HSK word's syllables
    must be one of its dictionary readings; any other character's syllable one of
    pypinyin's readings of it. A tone mark may be left off only where the reading
    itself is neutral (bà ba); tone numbers are refused.
    """
    text = sentence.strip()
    if any(c.isdigit() for c in pinyin):
        return ["pinyin uses tone numbers; write tone marks (bà ba, not ba4 ba)"]
    given = _syllables(pinyin)
    chars = [c for c in text if _is_hanzi(c)]
    if len(given) != len(chars):
        hint = "; write 儿 as its own syllable r (nǎ r)" if "儿" in chars else ""
        return [
            f"pinyin {pinyin!r} has {len(given)} syllables for {len(chars)} "
            "Chinese characters (one syllable per character, separated by spaces)"
            + hint
        ]
    dictionary = {c.fields["hanzi"]: c.fields.get("pinyin", "") for c in cards}
    pieces = [w for w in words if all(_is_hanzi(c) for c in w)]
    if sum(len(w) for w in pieces) != len(chars):
        pieces = chars  # the reading doesn't cover the sentence: check each character
    problems: list[str] = []
    at = 0
    for piece in pieces:
        mine = given[at : at + len(piece)]
        at += len(piece)
        if dictionary.get(piece):
            readings = [_syllables(r) for r in dictionary[piece].split("/")]
            if not any(
                len(r) == len(mine) and all(map(_fits, mine, r, piece))
                for r in readings
            ):
                problems.append(
                    f"pinyin {' '.join(mine)} for {piece} isn't one of its readings: "
                    f"{dictionary[piece]}"
                )
            continue
        for ch, syllable in zip(piece, mine, strict=True):
            options = _char_readings(ch)
            if not any(_fits(syllable, r, ch) for r in options):
                known = " / ".join(options) or "none known"
                problems.append(
                    f"pinyin {syllable} for {ch} isn't a reading of {ch}: {known}"
                )
    return problems


def layout_pinyin(sentence: str, pinyin: str) -> str:
    """The saved pinyin line: Claude's syllables, one per Chinese character, spaces
    between syllables, the sentence's own punctuation with no space around it."""
    syllables = [
        unicodedata.normalize("NFC", s.replace("v", "ü").replace("V", "Ü"))
        for s in _syllables(pinyin)
    ]
    out = ""
    after_syllable = False
    for ch in sentence.strip():
        if _is_hanzi(ch):
            if not syllables:
                break
            out += (" " if after_syllable else "") + syllables.pop(0)
            after_syllable = True
        elif not ch.isspace():
            out += ch
            after_syllable = False
    return out


# -- checking ------------------------------------------------------------------------


def _english_ok(text: str) -> bool:
    return 1 <= len(text) <= MAX_ENGLISH and bool(ENGLISH.fullmatch(text))


ENGLISH_REASON = (
    f"the English must be 1-{MAX_ENGLISH} characters: English letters, digits, "
    "spaces and normal punctuation"
)


def _sentence_problems(
    hanzi: str, pinyin: str, english: str, word: str, vocab: Vocab, cards: list[Card]
) -> list[str]:
    """Every problem with one sentence: the checker's, the pinyin's, the English's."""
    check = check_sentence(hanzi, word, vocab)
    problems = list(check.reasons)
    problems += pinyin_problems(hanzi, pinyin, check.words, cards)
    if not _english_ok(english):
        problems.append(ENGLISH_REASON)
    return problems


def _line_problems(
    line: SentenceLine, word: str, vocab: Vocab, cards: list[Card]
) -> list[str]:
    if not 1 <= len(line.sentences) <= MAX_SAVED:
        return [f"needs 1-{MAX_SAVED} sentences, has {len(line.sentences)}"]
    problems: list[str] = []
    if len({s.hanzi for s in line.sentences}) < len(line.sentences):
        problems.append("the same sentence is listed twice")
    for s in line.sentences:
        problems += [
            f"{s.hanzi}: {p}"
            for p in _sentence_problems(
                s.hanzi, s.pinyin, s.english, word, vocab, cards
            )
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


def _triples(given: object) -> list[tuple[str, str, str]]:
    """The (hanzi, pinyin, english) Claude gave for one word; malformed ones left out."""
    if not isinstance(given, list):
        return []
    triples = []
    for s in given:
        if not isinstance(s, dict):
            continue
        hanzi, pinyin, english = s.get("hanzi"), s.get("pinyin"), s.get("english")
        if all(isinstance(x, str) for x in (hanzi, pinyin, english)):
            triples.append(
                (hanzi.strip(), pinyin.strip(), english.translate(PLAIN).strip())
            )
    return triples


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


def read_lines(path: Path) -> list[SentenceLine]:
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


def _load_existing(
    out: Path,
    cards: list[Card],
    vocab: Vocab,
    removed: dict[str, set[str]] | None = None,
) -> tuple[dict[str, SentenceLine], dict[str, SentenceLine], bool]:
    """(done, saved, changed): current passing lines; every saved line to keep until
    it's replaced; whether the file needs rewriting (a line dropped or listed twice).

    A word listed twice keeps its first copy that passes the checks (else the first).
    Sentences on the removed list are taken out first; a line left empty is dropped.
    """
    removed = removed or {}
    if not out.exists():
        return {}, {}, False
    by_id = {c.id: c for c in cards}
    done: dict[str, SentenceLine] = {}
    saved: dict[str, SentenceLine] = {}
    usable: set[str] = set()  # ids whose kept line passes the checker
    changed = False
    for line in read_lines(out):
        if line.id not in by_id:
            print(f"Warning: dropped {line.id!r} from {out.name} (no longer a card)")
            changed = True
            continue
        listed = removed.get(line.id, set())
        kept = [s for s in line.sentences if s.hanzi not in listed]
        if len(kept) != len(line.sentences):
            changed = True
            if not kept:
                print(f"Will redo {line.id!r}: an audit removed all its sentences")
                continue
            line = line.model_copy(update={"sentences": kept})
        hanzi = by_id[line.id].fields["hanzi"]
        changed |= line.hanzi != hanzi
        line = line.model_copy(update={"hanzi": hanzi})
        problems = _line_problems(line, line.hanzi, vocab, cards)
        current = line.prompt_version == PROMPT_VERSION
        if line.id in saved:
            print(f"Warning: {line.id!r} is listed twice in {out.name}; kept one copy")
            changed = True
            better = line.id not in done and current
            if problems or (line.id in usable and not better):
                continue
        if not problems:
            usable.add(line.id)
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
    write_lines(
        out,
        [done.get(c.id) or saved[c.id] for c in cards if c.id in done or c.id in saved],
    )


def write_lines(path: Path, lines: list[SentenceLine]) -> None:
    """Save sentence lines in the file's one format (atomically). sentence_bank uses
    it too, so the shared file is always written the same way."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(
        json.dumps(line.model_dump(), ensure_ascii=False) + "\n" for line in lines
    )
    write_atomically(path, data.encode("utf-8"))


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
    with _LOG_LOCK:  # two background calls never interleave a line
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


# -- checking one word's reply ---------------------------------------------------------


def _by_id(items: list[object]) -> dict[str, object]:
    """Each word's sentences in a reply; the first entry for an id wins."""
    parsed: dict[str, object] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            parsed.setdefault(item["id"], item.get("sentences"))
    return parsed


REMOVED_REASON = "an audit removed this sentence; write a different one"


def _check_triples(
    triples: list[tuple[str, str, str]],
    word: str,
    vocab: Vocab,
    cards: list[Card],
    removed: set[str] | frozenset[str] = frozenset(),
) -> tuple[list[Sentence], list[tuple[str, list[str]]]]:
    """(good, bad): up to MAX_SENTENCES passing sentences, pinyin laid out; and the
    failing ones as "hanzi (pinyin: ...)" with their reasons. Repeats count once."""
    good: list[Sentence] = []
    bad: list[tuple[str, list[str]]] = []
    for hanzi, pinyin, english in triples:
        if len(good) == MAX_SENTENCES:
            break
        shown = f"{hanzi} (pinyin: {pinyin})"  # what a retry shows Claude
        if any(g.hanzi == hanzi for g in good) or any(b[0] == shown for b in bad):
            continue
        if hanzi in removed:  # on the removed list (ADR 0015): never saved
            bad.append((shown, [REMOVED_REASON]))
            continue
        problems = _sentence_problems(hanzi, pinyin, english, word, vocab, cards)
        if problems:
            bad.append((shown, problems))
            continue
        good.append(
            Sentence(hanzi=hanzi, pinyin=layout_pinyin(hanzi, pinyin), english=english)
        )
    return good, bad


# -- one word, during the quiz (ADR 0011) -----------------------------------------------


class WrittenSentences(BaseModel):
    """What write_one gives back: the sentences that passed every check."""

    model_config = ConfigDict(frozen=True)

    sentences: list[Sentence]
    model: str


# Seconds; one word takes about 4 s (measured 2026-11-04). Kept near the quiz's
# 15 s wait, so a call the quiz gave up on doesn't run on for long.
LIVE_TIMEOUT = 30


def write_one(
    card: Card,
    cards: list[Card],
    vocab: Vocab | None = None,
    ask: Callable[..., ClaudeReply] = ask_claude,
    timeout: float = LIVE_TIMEOUT,
    log: Path = LIVE_LOG_FILE,
) -> WrittenSentences:
    """One Claude call for one word, no retries: the sentences that pass every check
    (at most 2). [] if none pass or the reply is broken; a ClaudeError goes up.
    Writes only the log line (a failed log write is skipped: the sentences matter
    more); banking is sentence_bank's job."""
    if vocab is None:
        vocab = Vocab(cards)
    prompt = build_prompt([card], cards, card.level)
    reply = ask(
        prompt, model=MODEL, system=SYSTEM, json_schema=REPLY_SCHEMA, timeout=timeout
    )
    try:
        _log(log, reply, 1, 0)
    except OSError:
        pass  # e.g. the log is locked: not worth losing a good reply over
    try:
        items = parse_reply(reply.text).cards
    except ValueError:
        return WrittenSentences(sentences=[], model=reply.model)
    word = card.fields["hanzi"]
    good, _ = _check_triples(_triples(_by_id(items).get(card.id)), word, vocab, cards)
    return WrittenSentences(sentences=good, model=reply.model)


# -- the run -------------------------------------------------------------------------


class _Job:
    """Everything one run shares, so the steps below stay small."""

    def __init__(self, cards, vocab, ask, out, log, done, saved, run, removed) -> None:
        self.cards = cards
        self.vocab = vocab
        self.ask = ask
        self.out = out
        self.log = log
        self.done = done
        self.saved = saved
        self.run = run
        self.removed: dict[str, set[str]] = removed

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
        parsed = _by_id(items)
        failed: dict[str, list[tuple[str, list[str]]]] = {}
        for card in chunk:
            word = card.fields["hanzi"]
            good, bad = _check_triples(
                _triples(parsed.get(card.id)),
                word,
                self.vocab,
                self.cards,
                self.removed.get(card.id, set()),
            )
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
    removed: Path = REMOVED_FILE,
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
    listed = {word: set(items) for word, items in read_removed(removed).items()}
    vocab = Vocab(cards)
    done, saved, changed = _load_existing(out, cards, vocab, listed)
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

    job = _Job(cards, vocab, ask, out, log, done, saved, run, listed)
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
