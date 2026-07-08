import dataclasses
import json

import pytest

from deadlock_matches import items


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
