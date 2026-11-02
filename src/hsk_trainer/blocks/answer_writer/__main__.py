"""Command line: uv run python -m hsk_trainer.blocks.answer_writer --limit 20 [--dry-run]"""

import argparse
import sys

from hsk_trainer.blocks.answer_writer import ROOT, write_answers
from quizkit.claude import ClaudeError
from quizkit.files import load_cards

CARDS_FILE = ROOT / "data" / "processed" / "cards.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="only N cards")
    parser.add_argument("--dry-run", action="store_true", help="show, don't send")
    parser.add_argument("--chunk-size", type=int, default=40)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # hanzi through Windows pipes
    try:
        write_answers(
            load_cards(CARDS_FILE),
            limit=args.limit,
            dry_run=args.dry_run,
            chunk_size=args.chunk_size,
        )
    except ValueError as err:  # AnswerFileError, or a bad --limit / --chunk-size
        print(f"Stopped: {err}")
        return 1
    except ClaudeError as err:
        print(f"Stopped: {err}\nWork so far is saved; run again to continue.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
