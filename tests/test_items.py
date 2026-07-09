import dataclasses
import datetime as dt
import json

import pytest

from deadlock_matches import history, items


def _write_history(path):
    """Write a two-era item history where item 10 rose from 500 to 800 souls on 2026-01-04."""

    def era(cost):
        record = {
            "id": 10,
            "name": "Foo",
            "class_name": "upgrade_foo",
            "cost": cost,
            "slot": "weapon",
            "tier": 1,
        }
        return {"10": record}

    history.write(
        path,
        [
            {"from": "2026-01-01T00:00:00", "build": 1, "records": era(500)},
            {"from": "2026-01-04T00:00:00", "build": 4, "records": era(800)},
        ],
    )


def test_item_asof_picks_the_era_in_effect(tmp_path):
    path = tmp_path / "item_history.parquet"
    _write_history(path)

    assert items.item_asof(10, dt.datetime(2026, 1, 2), path).cost == 500
    assert items.item_asof(10, dt.datetime(2026, 1, 5), path).cost == 800


def test_item_asof_older_than_history_gets_earliest(tmp_path):
    path = tmp_path / "item_history.parquet"
    _write_history(path)

    assert items.item_asof(10, dt.datetime(2025, 12, 31), path).cost == 500


def test_item_asof_unknown_id_is_none(tmp_path):
    path = tmp_path / "item_history.parquet"
    _write_history(path)

    assert items.item_asof(999, dt.datetime(2026, 1, 5), path) is None


def test_item_asof_without_history_falls_back_to_bundled(tmp_path):
    ee = items.item_by_name("Escalating Exposure")
    missing = tmp_path / "none.parquet"

    assert items.item_asof(ee.id, dt.datetime(2026, 1, 5), missing).cost == ee.cost
    assert items.item_asof(999999, dt.datetime(2026, 1, 5), missing) is None


def test_committed_item_history_newest_matches_bundle():
    today = dt.date(2026, 7, 9)

    assert history.has_history(items.ITEM_HISTORY_PARQUET)

    current = items.item_map()
    resolved = {i: items.item_asof(i, today) for i in current}
    mismatched = [
        i
        for i, it in current.items()
        if resolved[i] and (resolved[i].cost != it.cost or resolved[i].tier != it.tier)
    ]

    assert not mismatched


def test_item_map_loads_real_file():
    m = items.item_map()
    ee = m[3005970438]

    assert ee.name == "Escalating Exposure"
    assert ee.cost == 6400
    assert ee.slot == "spirit"
    assert all(isinstance(k, int) for k in m)


def test_item_name_known_and_unknown():
    assert items.item_name(3005970438) == "Escalating Exposure"
    assert items.item_name(999999) == "id999999"


def test_item_by_name():
    ee = items.item_by_name("Escalating Exposure")

    assert ee is not None
    assert ee.id == 3005970438
    assert items.item_by_name("no such item") is None


def test_from_record_ignores_extra_keys():
    rec = {
        "id": 1,
        "name": "Basic Magazine",
        "cost": 500,
        "slot": "weapon",
        "tier": 1,
        "something_unmodeled": {"a": 1},
    }

    it = items.Item.from_record(rec)

    assert it.name == "Basic Magazine"
    assert it.cost == 500
    assert it.is_active is False


def test_custom_path(tmp_path):
    p = tmp_path / "i.json"
    p.write_text(json.dumps([{"id": 7, "name": "Headshot Booster", "cost": 500}]))

    assert items.item_name(7, p) == "Headshot Booster"


def test_item_is_frozen():
    it = items.item_map()[3005970438]

    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(it, "name", "test")
