"""normalizer: Turn the raw HSK word lists (data/raw/hsk3_2026/) into Card records, one per word, saved to data/processed/cards.jsonl.

See SPEC.md in this folder (ADR 0003).
"""

from quizkit.blocks.base import BlockSpec

BLOCK_SPEC = BlockSpec(
    name="normalizer",
    kind="script",
    goal="Turn the raw HSK word lists (data/raw/hsk3_2026/) into Card records, one per word, saved to data/processed/cards.jsonl.",
    inputs=["src: Path", "dest: Path"],
    outputs=["list[Card]"],
)


def run() -> None:
    """TODO: implement (see SPEC.md)."""
    raise NotImplementedError("normalizer is not built yet")
