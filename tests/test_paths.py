from pathlib import Path

from deadlock_matches import extract, paths


def test_linux_dirs(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")

    assert paths.data_dir() == Path.home() / ".local/share"
    assert paths.cache_dir() == Path.home() / ".cache/deadlock-matches"


def test_windows_dirs(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/x/AppData/Local")

    assert paths.data_dir() == Path("C:/Users/x/AppData/Local")
    assert paths.cache_dir() == Path("C:/Users/x/AppData/Local/deadlock-matches/cache")


def test_windows_dirs_fallback(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert paths.data_dir() == Path.home() / "AppData/Local"


def test_linux_candidates_order():
    cands = extract._linux_candidates()

    assert cands[0] == Path.home() / ".steam/steam/appcache/httpcache"
    assert len(cands) == 3


def test_windows_candidates_have_default_install():
    cands = extract._windows_candidates()

    assert cands[-1] == Path("C:/Program Files (x86)/Steam/appcache/httpcache")
