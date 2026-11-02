# Block: `fetcher`

> **In plain words:** downloads the 3 pinned HSK word-list files (bands 1–3) plus the licence, and checks they're exactly the files and size we expect.

## Goal
Download the 3 pinned HSK word-list files (bands 1–3) and check they're exactly the files and size we expect, so every later step starts from the same trusted data (ADR 0004).

## Kind
script: downloading and checking size + fingerprint is mechanical, and code can check it 100%.

## Inputs
- `dest: Path`: the folder to save into (optional, default `data/raw/hsk3_2026/`)
- Nothing else. The source, pinned version, file names, sizes and fingerprints are a built-in "shopping list" (`FILES` in the code), which follows ADR 0004.
- For tests only: `files=` (a small fake shopping list) and `fetch=` (a fake downloader), so tests never use the internet.

## Outputs
- `list[Path]`: the 4 saved files in `dest`: `1.json`, `2.json`, `3.json`, `LICENSE`
- Files that are already present and correct are not downloaded again

## Tools
- `quizkit.download.download_verified()`: the generic "download + check size and fingerprint" helper (reusable by any quiz)
- Python's built-in `urllib` and `hashlib`: no extra libraries

## Failure modes
All errors are a `quizkit.download.DownloadError` whose message names the file.
- No internet / download fails → stop with a clear error, save nothing for that file
- Wrong size or fingerprint (the file changed) → stop with an error naming the file, save nothing
- File already present and correct → skip it (no re-download)
- File already present but wrong (corrupted) → download again and check it. If the new download is also bad → error, and the old file is left alone (a bad file is never swapped in)
- Download dies halfway → never leave a half-written file behind (not even a temp file)
- A later file fails → stop there. Earlier files are kept (they were already checked)
- Save folder missing → create it

## How to test
- Tests never use the internet: they use a fake downloader with small sample files
- One test per failure mode above, plus "a good file gets saved"
- Real check, by hand (not in CI): `uv run python -m hsk_trainer.blocks.fetcher` fetches all 4 files and passes every check
