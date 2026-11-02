"""fetcher: Download the 3 pinned HSK word-list files (bands 1-3) and check they are
exactly the files and size we expect.

See SPEC.md in this folder (ADR 0003) and ADR 0004 (the source).
Run by hand: uv run python -m hsk_trainer.blocks.fetcher
"""

from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from quizkit.blocks.base import BlockSpec
from quizkit.download import download_verified, http_get

BLOCK_SPEC = BlockSpec(
    name="fetcher",
    kind="script",
    goal="Download the 3 pinned HSK word-list files (bands 1-3) and check they are "
    "exactly the files and size we expect",
    inputs=["dest: Path"],
    outputs=["list[Path]"],
)

# ---- The "shopping list" (follows ADR 0004) ------------------------------------------
SOURCE_REPO = "drkameleon/complete-hsk-vocabulary"
PINNED_SHA = "7ac65bf1a6387d35f1ade478906172a19311c7f9"
DEFAULT_DEST = Path("data/raw/hsk3_2026")


class PinnedFile(BaseModel):
    """One file to fetch: where it is in the source, what to save it as, and what it must be."""

    model_config = ConfigDict(frozen=True)

    source_path: str
    save_as: str
    size: int
    sha256: str


FILES: list[PinnedFile] = [
    PinnedFile(
        source_path="wordlists/exclusive/newest/1.json",
        save_as="1.json",
        size=281_274,
        sha256="0afa5137b68b9386bd83e4953fb39afaf7fb536b9e3f77a727b63bf7850c5ce4",
    ),
    PinnedFile(
        source_path="wordlists/exclusive/newest/2.json",
        save_as="2.json",
        size=209_050,
        sha256="1457ff04de7af612e43d21b626544cc26dde6c71e08e223c6ffc30c82496d66e",
    ),
    PinnedFile(
        source_path="wordlists/exclusive/newest/3.json",
        save_as="3.json",
        size=423_216,
        sha256="6dd60850ad8c815c06f8e1f4291dd1b491a33a3e9b8db571f8f507b53968d3b1",
    ),
    PinnedFile(
        source_path="LICENSE",
        save_as="LICENSE",
        size=1_075,
        sha256="21094287f6e487f6978cf240c67603e4a0e9f341c6e732558d052feb44210c8f",
    ),
]


def url_for(file: PinnedFile) -> str:
    """The download address: source + pinned version + file."""
    return f"https://raw.githubusercontent.com/{SOURCE_REPO}/{PINNED_SHA}/{file.source_path}"


def run(
    dest: Path = DEFAULT_DEST,
    *,
    files: Sequence[PinnedFile] = FILES,
    fetch: Callable[[str], bytes] = http_get,
) -> list[Path]:
    """Fetch every pinned file into `dest` and return the saved paths.

    `files` and `fetch` exist so tests can use small fake files and no internet.
    Stops at the first problem with a DownloadError; earlier (checked) files are kept.
    """
    dest = Path(
        dest
    )  # download_verified creates the folder (errors become DownloadError)
    saved: list[Path] = []
    for file in files:
        path = dest / file.save_as
        download_verified(
            url_for(file), path, size=file.size, sha256=file.sha256, fetch=fetch
        )
        saved.append(path)
    return saved
