import datetime as dt

from deadlock_matches import history, statues


def statue_rec(value):
    return {
        "id": 5,
        "class_name": "hp_permanent_pickup_lv2",
        "stat": "health_max",
        "value": value,
    }


STATUE_STATES = [
    {
        "from": "2026-01-01T00:00:00",
        "build": 100,
        "records": {"hp_permanent_pickup_lv2": statue_rec(25)},
    },
    {
        "from": "2026-02-01T00:00:00",
        "build": 200,
        "records": {"hp_permanent_pickup_lv2": statue_rec(20)},
    },
]


def test_parse_pickup_splits_buff_and_level():
    assert statues.parse_pickup("hp_permanent_pickup") == ("hp", 1)
    assert statues.parse_pickup("cd_permanent_pickup_lv2") == ("cd", 2)
    assert statues.parse_pickup("wp_permanent_pickup_lv3") == ("wp", 3)


def test_parse_pickup_crate_power_ups_have_no_level():
    assert statues.parse_pickup("gun_powerup_pickup") == ("gun", None)
    assert statues.parse_pickup("casting_powerup_pickup") == ("casting", None)


def test_parse_pickup_unrecognized_names():
    assert statues.parse_pickup("citadel_item_pickup_rejuv") == (None, None)
    assert statues.parse_pickup("") == (None, None)


def test_is_statue():
    assert statues.is_statue("spirit_permanent_pickup_lv2")
    assert not statues.is_statue("movement_powerup_pickup")
    assert not statues.is_statue("dropped_soul_orb")


def test_statue_map_loads_the_bundled_snapshot():
    catalog = statues.statue_map()
    families = {s.buff for s in catalog.values()}
    levels = {s.level for s in catalog.values()}

    assert families == {"hp", "spirit", "wp", "firerate", "ammo", "cd"}
    assert levels == {1, 2, 3}
    assert all(s.stat is not None for s in catalog.values())
    assert all(s.value is not None and s.value > 0 for s in catalog.values())


def test_statue_map_asof_picks_the_era_in_effect(tmp_path):
    path = tmp_path / "statue_history.parquet"
    history.write(path, STATUE_STATES)

    early = statues.statue_map_asof(dt.datetime(2026, 1, 2), path)
    late = statues.statue_map_asof(dt.datetime(2026, 2, 5), path)

    assert early["hp_permanent_pickup_lv2"].value == 25
    assert late["hp_permanent_pickup_lv2"].value == 20


def test_statue_map_asof_derives_buff_and_level(tmp_path):
    path = tmp_path / "statue_history.parquet"
    history.write(path, STATUE_STATES)

    resolved = statues.statue_map_asof(dt.datetime(2026, 1, 2), path)
    entry = resolved["hp_permanent_pickup_lv2"]

    assert entry.buff == "hp"
    assert entry.level == 2
    assert entry.stat == "health_max"


def test_statue_map_asof_without_history_falls_back_to_bundled(tmp_path):
    missing = tmp_path / "none.parquet"

    resolved = statues.statue_map_asof(dt.datetime(2026, 1, 5), missing)

    assert resolved == statues.statue_map()
