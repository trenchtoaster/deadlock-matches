import pytest

from deadlock_matches import paths


@pytest.fixture(autouse=True)
def _no_assets_history(tmp_path, monkeypatch):
    """Point the dated-snapshot folder somewhere empty so tests never see real history."""
    monkeypatch.setattr(paths, "assets_history_dir", lambda: tmp_path / "assets-history")
