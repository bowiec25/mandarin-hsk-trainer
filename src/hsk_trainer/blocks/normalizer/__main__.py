"""Run the normalizer by hand: uv run python -m hsk_trainer.blocks.normalizer"""

import sys
from collections import Counter

from hsk_trainer.blocks.normalizer import DEFAULT_DEST, NormalizeError, run

try:
    cards = run()
except NormalizeError as err:
    print(f"Error: {err}", file=sys.stderr)
    sys.exit(1)

per_band = Counter(card.level for card in cards)
bands = ", ".join(f"band {b}: {n}" for b, n in sorted(per_band.items()))
print(f"OK {len(cards)} cards ({bands}) -> {DEFAULT_DEST.as_posix()}")
