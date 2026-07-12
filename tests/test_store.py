import json

import pytest

from deadlock_matches.assets import history, items, snapshots, store


@pytest.fixture(autouse=True)
def _clear_item_cache():
    items.item_map.cache_clear()
    yield
    items.item_map.cache_clear()


def test_read_path_prefers_user_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "store_dir", lambda: tmp_path)
    (tmp_path / "items.json").write_text("[]", encoding="utf-8")

    assert store.read_path("items.json") == tmp_path / "items.json"


def test_read_path_falls_back_to_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "store_dir", lambda: tmp_path)

    assert store.read_path("items.json") == store.seed_path("items.json")


def test_write_path_targets_user_store_and_creates_parent(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "store_dir", lambda: tmp_path / "assets")

    target = store.write_path("items.json")

    assert target == tmp_path / "assets" / "items.json"
    assert target.parent.is_dir()


def test_item_map_reads_user_store_overlay(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "store_dir", lambda: tmp_path)
    rec = {"id": 999999, "name": "Overlay Item", "is_active": False}
    (tmp_path / "items.json").write_text(json.dumps([rec]), encoding="utf-8")

    got = items.item_map()

    assert 999999 in got
    assert got[999999].name == "Overlay Item"


def test_build_asset_history_resumes_from_seed(tmp_path, monkeypatch):
    seed = tmp_path / "seed.parquet"
    history.write(
        seed,
        [{"from": "2026-01-01T00:00:00", "build": 100, "records": {"1": {"id": 1, "v": "a"}}}],
    )
    target = tmp_path / "user.parquet"

    monkeypatch.setattr(
        snapshots, "client_version_dates", lambda *a, **k: {100: "2026-01-01", 200: "2026-02-01"}
    )
    loads = {100: {"1": {"id": 1, "v": "a"}}, 200: {"1": {"id": 1, "v": "b"}}}

    eras = snapshots.build_asset_history(lambda b: loads[b], target, resume_from=seed)

    assert eras == 2
    assert [s["build"] for s in history.read_states(target)] == [100, 200]
    assert [s["build"] for s in history.read_states(seed)] == [100]


def test_is_source_checkout_false_outside_package(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "SEED_DIR", tmp_path / "pkg" / "data")

    assert store.is_source_checkout() is False


def test_is_source_checkout_true_for_own_pyproject(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "deadlock-matches"\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        store, "SEED_DIR", tmp_path / "src" / "deadlock_matches" / "assets" / "data"
    )

    assert store.is_source_checkout() is True


def test_is_source_checkout_rejects_unrelated_pyproject(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "some-other-project"\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        store,
        "SEED_DIR",
        tmp_path / ".venv" / "site-packages" / "deadlock_matches" / "assets" / "data",
    )

    assert store.is_source_checkout() is False
