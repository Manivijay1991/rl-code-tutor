import pytest

from coding_tutor.cms import fetch


def test_fetch_downloads_and_writes(tmp_path):
    calls = []
    path = fetch.fetch("a/b.zip", "http://x/b.zip", raw_dir=tmp_path, get=lambda url: calls.append(url) or b"data")
    assert path.read_bytes() == b"data" and calls == ["http://x/b.zip"]


def test_fetch_skips_existing(tmp_path):
    (tmp_path / "f.zip").write_bytes(b"old")
    path = fetch.fetch("f.zip", "http://x", raw_dir=tmp_path, get=lambda url: pytest.fail("should not download"))
    assert path.read_bytes() == b"old"


def test_fetch_force_redownloads(tmp_path):
    (tmp_path / "f.zip").write_bytes(b"old")
    fetch.fetch("f.zip", "http://x", force=True, raw_dir=tmp_path, get=lambda url: b"new")
    assert (tmp_path / "f.zip").read_bytes() == b"new"


def test_fetch_propagates_download_errors(tmp_path):
    def boom(url):
        raise OSError("offline")

    with pytest.raises(OSError, match="offline"):
        fetch.fetch("f.zip", "http://x", raw_dir=tmp_path, get=boom)
    assert not (tmp_path / "f.zip").exists()


def test_sources_are_cms_https():
    assert all(url.startswith("https://www.cms.gov/") for url in fetch.SOURCES.values())
