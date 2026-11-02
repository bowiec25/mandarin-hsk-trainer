"""Tests for the fetcher block: contract (ID card + SPEC) and behaviour (from SPEC.md)."""

import hashlib
from pathlib import Path

import pytest

import hsk_trainer.blocks.fetcher as block
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.download import DownloadError

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "fetcher"
    assert block.BLOCK_SPEC.kind == "script"


def test_spec_md_has_every_section():
    assert missing_spec_sections(SPEC_MD) == []


def test_inputs_and_outputs_match_spec():
    """The code's ID card (BLOCK_SPEC) and the job description (SPEC.md) agree."""
    for field, section in [("inputs", "Inputs"), ("outputs", "Outputs")]:
        listed = getattr(block.BLOCK_SPEC, field)
        text = spec_section(SPEC_MD, section)
        for item in listed:
            assert item in text, (
                f"BLOCK_SPEC.{field} has {item!r}, not in SPEC.md {section}"
            )
        if "TODO" not in text:  # once the SPEC section is filled in...
            assert listed, (
                f"SPEC.md {section} is filled in: copy it into BLOCK_SPEC.{field}"
            )


# ---- Behaviour (from SPEC.md), using small fake files and a fake downloader ----------

CONTENT = {"a.json": b'["one"]', "b.json": b'["two", "three"]'}


def pinned(name: str, data: bytes) -> block.PinnedFile:
    return block.PinnedFile(
        source_path=f"lists/{name}",
        save_as=name,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


FAKE_FILES = [pinned(n, d) for n, d in CONTENT.items()]


class FakeFetch:
    """Serves CONTENT by URL ending; `override` swaps in bad bytes or an error."""

    def __init__(self, override: dict[str, bytes | Exception] | None = None):
        self.override = override or {}
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        name = url.rsplit("/", 1)[-1]
        result = self.override.get(name, CONTENT[name])
        if isinstance(result, Exception):
            raise result
        return result


def fetch_all(dest: Path, fetch: FakeFetch) -> list[Path]:
    return block.run(dest=dest, files=FAKE_FILES, fetch=fetch)


def test_default_shopping_list_is_the_four_pinned_files():
    assert block.DEFAULT_DEST == Path("data/raw/hsk3_2026")
    names = [f.save_as for f in block.FILES]
    assert names == ["1.json", "2.json", "3.json", "LICENSE"]


def test_good_files_are_saved_and_returned(tmp_path):
    paths = fetch_all(tmp_path, FakeFetch())
    assert paths == [tmp_path / "a.json", tmp_path / "b.json"]
    for name, data in CONTENT.items():
        assert (tmp_path / name).read_bytes() == data


def test_fetch_uses_the_pinned_url(tmp_path):
    fetch = FakeFetch()
    fetch_all(tmp_path, fetch)
    assert fetch.calls == [block.url_for(f) for f in FAKE_FILES]
    assert all(block.PINNED_SHA in url for url in fetch.calls)


def test_download_failure_stops_with_clear_error_and_saves_nothing(tmp_path):
    fetch = FakeFetch({"a.json": OSError("no internet")})
    with pytest.raises(DownloadError, match="a.json"):
        fetch_all(tmp_path, fetch)
    assert not (tmp_path / "a.json").exists()


def test_wrong_size_stops_with_error_naming_file(tmp_path):
    fetch = FakeFetch({"b.json": CONTENT["b.json"] + b" "})
    with pytest.raises(DownloadError, match="b.json"):
        fetch_all(tmp_path, fetch)
    assert not (tmp_path / "b.json").exists()
    # "A later file fails → stop there. Earlier files are kept"
    assert (tmp_path / "a.json").read_bytes() == CONTENT["a.json"]


def test_wrong_fingerprint_stops_with_error_naming_file(tmp_path):
    bad = b"X" + CONTENT["b.json"][1:]
    with pytest.raises(DownloadError, match="b.json"):
        fetch_all(tmp_path, FakeFetch({"b.json": bad}))
    assert not (tmp_path / "b.json").exists()
    assert (tmp_path / "a.json").read_bytes() == CONTENT["a.json"]  # earlier file kept


def test_present_and_correct_files_are_skipped(tmp_path):
    for name, data in CONTENT.items():
        (tmp_path / name).write_bytes(data)
    fetch = FakeFetch()
    paths = fetch_all(tmp_path, fetch)
    assert fetch.calls == []
    assert paths == [tmp_path / "a.json", tmp_path / "b.json"]


def test_present_but_corrupted_file_is_downloaded_again(tmp_path):
    (tmp_path / "a.json").write_bytes(CONTENT["a.json"])
    (tmp_path / "b.json").write_bytes(b"corrupted")
    fetch = FakeFetch()
    fetch_all(tmp_path, fetch)
    assert fetch.calls == [block.url_for(FAKE_FILES[1])]
    assert (tmp_path / "b.json").read_bytes() == CONTENT["b.json"]


def test_download_dying_halfway_leaves_no_partial_file(tmp_path):
    fetch = FakeFetch({"a.json": ConnectionResetError("connection reset")})
    with pytest.raises(DownloadError):
        fetch_all(tmp_path, fetch)
    assert list(tmp_path.iterdir()) == []


def test_creates_dest_folder_if_missing(tmp_path):
    dest = tmp_path / "raw" / "hsk"
    paths = fetch_all(dest, FakeFetch())
    assert all(p.parent == dest and p.exists() for p in paths)


def test_corrupted_file_and_bad_redownload_leaves_old_file_alone(tmp_path):
    """SPEC: if the new download is also bad → error, old file left alone."""
    (tmp_path / "a.json").write_bytes(b"corrupted")
    fetch = FakeFetch({"a.json": b"also bad"})
    with pytest.raises(DownloadError, match="a.json"):
        fetch_all(tmp_path, fetch)
    assert (tmp_path / "a.json").read_bytes() == b"corrupted"


def test_folder_in_the_way_gives_clear_error_naming_file(tmp_path):
    """Every error is a DownloadError naming the file, even odd disk problems."""
    (tmp_path / "a.json").mkdir()  # a folder sits where a.json should be saved
    with pytest.raises(DownloadError, match="a.json"):
        fetch_all(tmp_path, FakeFetch())


def test_save_folder_blocked_by_a_file_gives_clear_error(tmp_path):
    blocker = tmp_path / "raw"
    blocker.write_text("not a folder", encoding="utf-8")
    with pytest.raises(DownloadError, match="a.json"):
        fetch_all(blocker, FakeFetch())
