"""download_verified: download a file and check size + fingerprint (fake fetch, no internet)."""

import hashlib
from pathlib import Path
from urllib.error import URLError

import pytest

from quizkit.download import DownloadError, download_verified

URL = "https://example.test/words.json"
GOOD = b'{"hello": "world"}'
SIZE = len(GOOD)
SHA = hashlib.sha256(GOOD).hexdigest()


class FakeFetch:
    """Returns fixed bytes (or raises) and counts how often it was called."""

    def __init__(self, result: bytes | Exception = GOOD):
        self.result = result
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def get(dest: Path, fetch: FakeFetch) -> bool:
    return download_verified(URL, dest, size=SIZE, sha256=SHA, fetch=fetch)


def test_good_file_is_saved(tmp_path):
    dest = tmp_path / "words.json"
    fetch = FakeFetch()
    assert get(dest, fetch) is True
    assert dest.read_bytes() == GOOD
    assert fetch.calls == [URL]


@pytest.mark.parametrize("err", [URLError("no internet"), OSError("network down")])
def test_download_failure_raises_and_saves_nothing(tmp_path, err):
    dest = tmp_path / "words.json"
    with pytest.raises(DownloadError):
        get(dest, FakeFetch(err))
    assert list(tmp_path.iterdir()) == []


def test_wrong_size_raises_naming_file_and_saves_nothing(tmp_path):
    dest = tmp_path / "words.json"
    with pytest.raises(DownloadError, match="words.json"):
        get(dest, FakeFetch(GOOD + b"extra"))
    assert list(tmp_path.iterdir()) == []


def test_wrong_fingerprint_raises_naming_file_and_saves_nothing(tmp_path):
    dest = tmp_path / "words.json"
    same_size_different = b"X" + GOOD[1:]
    assert len(same_size_different) == SIZE
    with pytest.raises(DownloadError, match="words.json"):
        get(dest, FakeFetch(same_size_different))
    assert list(tmp_path.iterdir()) == []


def test_present_and_correct_file_is_not_downloaded_again(tmp_path):
    dest = tmp_path / "words.json"
    dest.write_bytes(GOOD)
    fetch = FakeFetch()
    assert get(dest, fetch) is False
    assert fetch.calls == []
    assert dest.read_bytes() == GOOD


def test_present_but_corrupted_file_is_downloaded_again(tmp_path):
    dest = tmp_path / "words.json"
    dest.write_bytes(b"corrupted")
    fetch = FakeFetch()
    assert get(dest, fetch) is True
    assert fetch.calls == [URL]
    assert dest.read_bytes() == GOOD


def test_download_dying_halfway_leaves_no_partial_file(tmp_path):
    """A connection reset mid-download leaves no file and no temp file behind."""
    dest = tmp_path / "words.json"
    with pytest.raises(DownloadError):
        get(dest, FakeFetch(ConnectionResetError("connection reset")))
    assert list(tmp_path.iterdir()) == []


def test_truncated_download_leaves_no_partial_file(tmp_path):
    """Only half the bytes arrive: rejected, nothing (not even a temp file) left."""
    dest = tmp_path / "words.json"
    with pytest.raises(DownloadError, match="words.json"):
        get(dest, FakeFetch(GOOD[: SIZE // 2]))
    assert list(tmp_path.iterdir()) == []


def test_corrupted_file_and_bad_redownload_leaves_old_file_alone(tmp_path):
    dest = tmp_path / "words.json"
    dest.write_bytes(b"corrupted")
    with pytest.raises(DownloadError, match="words.json"):
        download_verified(URL, dest, size=SIZE, sha256=SHA, fetch=FakeFetch(b"bad"))
    assert dest.read_bytes() == b"corrupted"


def test_write_failing_halfway_leaves_no_temp_file(tmp_path, monkeypatch):
    """The clean-up path really runs: the final swap-in fails, so no .part file may remain."""
    import os

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    dest = tmp_path / "words.json"
    with pytest.raises(DownloadError, match="words.json"):
        download_verified(URL, dest, size=SIZE, sha256=SHA, fetch=FakeFetch())
    assert list(tmp_path.iterdir()) == []
