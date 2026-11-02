"""Word-count test (M2 Step 6, ADR 0004): the committed cards.jsonl has the right words.

Reads the real data file, so CI notices if the data or the normalizer changes by accident.
"""

from collections import Counter
from pathlib import Path

import pytest

from hsk_trainer.blocks.normalizer import DEFAULT_DEST, DEFAULT_SRC, run
from quizkit.models import Card

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / DEFAULT_DEST
RAW = ROOT / DEFAULT_SRC

# ADR 0004: exact counts in the pinned 2026 syllabus (new words per band)...
EXPECTED_NEW = {1: 294, 2: 197, 3: 487}
# ...and the official round targets (cumulative: band 2 includes band 1's words).
OFFICIAL_CUMULATIVE = {1: 300, 2: 500, 3: 1000}
TOLERANCE = 0.05


@pytest.fixture(scope="module")
def cards() -> list[Card]:
    lines = CARDS.read_text(encoding="utf-8").splitlines()
    return [Card.model_validate_json(line) for line in lines]


def cumulative(per_band: dict[int, int]) -> dict[int, int]:
    total, out = 0, {}
    for band in sorted(per_band):
        total += per_band[band]
        out[band] = total
    return out


def test_exact_count_per_band(cards):
    assert dict(Counter(c.level for c in cards)) == EXPECTED_NEW


def test_exact_cumulative_counts(cards):
    per_band = dict(Counter(c.level for c in cards))
    assert cumulative(per_band) == {1: 294, 2: 491, 3: 978}


@pytest.mark.parametrize("band", [1, 2, 3])
def test_within_5_percent_of_official_target(cards, band):
    have = cumulative(dict(Counter(c.level for c in cards)))[band]
    target = OFFICIAL_CUMULATIVE[band]
    assert abs(have - target) <= TOLERANCE * target, (
        f"band {band}: {have} words, official target {target} (±{TOLERANCE:.0%})"
    )


def test_every_word_is_unique(cards):
    assert len({c.id for c in cards}) == len(cards)


def test_committed_file_is_up_to_date(tmp_path):
    """Re-running the normalizer gives exactly the committed file (no stale data)."""
    fresh = tmp_path / "cards.jsonl"
    run(src=RAW, dest=fresh)
    assert fresh.read_bytes() == CARDS.read_bytes(), (
        "cards.jsonl is stale: run `uv run python -m hsk_trainer.blocks.normalizer` "
        "and commit the result"
    )
