"""Generic helper: download a file and check its size + SHA-256 fingerprint.

Reusable by any quiz: give it a URL, where to save, and the expected size + fingerprint.
"""

import hashlib
import urllib.request
from collections.abc import Callable
from pathlib import Path

from quizkit.files import write_atomically


class DownloadError(RuntimeError):
    """The download failed, or the file isn't the one we expected."""


def http_get(url: str) -> bytes:
    """Fetch a URL and return its bytes (the real, internet-using downloader)."""
    with urllib.request.urlopen(url, timeout=30) as response:  # pinned https URLs only
        return response.read()


def _matches(data: bytes, size: int, sha256: str) -> bool:
    return len(data) == size and hashlib.sha256(data).hexdigest() == sha256


def download_verified(
    url: str,
    dest: Path,
    *,
    size: int,
    sha256: str,
    fetch: Callable[[str], bytes] = http_get,
) -> bool:
    """Make sure `dest` holds exactly the expected file.

    Returns True if it downloaded the file, or False if a correct copy was already there.
    Raises DownloadError if the download fails or the size/fingerprint don't match.
    `fetch` can be swapped for a fake in tests, so no internet is needed.
    """
    dest = Path(dest)
    try:
        if dest.is_file() and _matches(dest.read_bytes(), size, sha256):
            return False  # already there and correct
    except OSError:
        pass  # can't read the existing copy: treat it as wrong and download again

    try:
        data = fetch(url)
    except Exception as err:  # network errors, timeouts, connection resets…
        raise DownloadError(f"{dest.name}: download failed ({err})") from err

    if len(data) != size:
        raise DownloadError(
            f"{dest.name}: wrong size ({len(data):,} bytes, expected {size:,})"
        )
    if hashlib.sha256(data).hexdigest() != sha256:
        raise DownloadError(
            f"{dest.name}: fingerprint doesn't match the pinned version"
        )

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_atomically(dest, data)
    except OSError as err:  # disk full, no permission…
        raise DownloadError(f"{dest.name}: could not save ({err})") from err
    return True
