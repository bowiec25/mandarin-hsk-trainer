"""Run the fetcher by hand: uv run python -m hsk_trainer.blocks.fetcher"""

import sys

from hsk_trainer.blocks.fetcher import run
from quizkit.download import DownloadError

try:
    for path in run():
        print(f"OK {path.as_posix()}")
except DownloadError as err:
    print(f"Error: {err}", file=sys.stderr)
    sys.exit(1)
