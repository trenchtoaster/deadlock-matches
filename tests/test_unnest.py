import polars as pl

from deadlock_matches import schemas
from deadlock_matches.assets import history, items, unnest


def item_rec(cost, components=()):
    return {
        "id": 7,
        "name": "Test Item",
        "class_name": "upgrade_test",
        "cost": cost,
        "slot": "weapon",
        "tier": 1,
        "is_active": False,
        "description": "desc",
        "components": list(components),
    }


ITEM_STATES = [
    {"from": "2026-01-01T00:00:00", "build": 100, "records": {"7": item_rec(500, ["upgrade_a"])}},
    {
        "from": "2026-02-01T00:00:00",
        "build": 200,
        "records": {"7": item_rec(800, ["upgrade_a", "upgrade_b"])},
    },
]


def hero_rec(hp):
    return {
        "id": 1,
        "name": "Hero",
        "class_name": "hero_test",
        "hero_type": "melee",
        "gun_tag": None,
        "complexity": 1,
        "player_selectable": True,
        "disabled": False,
        "stats": {"max_health": hp},
        "level_up": {"tech_power": 1.5},
        "levels": [{"level": 1, "required_souls": 0, "standard_upgrade": True, "currencies": []}],
    }


HERO_STATES = [
    {"from": "2026-01-01T00:00:00", "build": 100, "records": {"1": hero_rec(600)}},
    {"from": "2026-02-01T00:00:00", "build": 200, "records": {"1": hero_rec(650)}},
]


ABILITY_RECS = {
    "citadel_ability_x": {
        "id": 5,
        "name": "Dash",
        "class_name": "citadel_ability_x",
        "hero": 1,
        "kind": "ability",
        "description": "d",
        "properties": {"impact_damage": 60},
        "scaling": {"impact_damage": {"stat": "tech_power", "scale": 1.0}},
        "upgrades": [[{"property": "impact_damage", "bonus": 10}], []],
        "tier_descriptions": [],
    },
    "citadel_weapon_x": {
        "id": 6,
        "name": "Gun",
        "class_name": "citadel_weapon_x",
        "hero": 1,
        "kind": "weapon",
        "weapon": {"bullet_damage": 10, "clip_size": 20},
    },
}

ABILITY_STATES = [{"from": "2026-01-01T00:00:00", "build": 100, "records": ABILITY_RECS}]

RANK_STATES = [
    {"from": "2026-01-01T00:00:00", "build": 100, "records": {"1": {"tier": 1, "name": "Initiate"}}}
]


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


def test_item_tables_flatten_each_era(tmp_path):
    path = tmp_path / "item_history.parquet"
    history.write(path, ITEM_STATES)

    tables = unnest.item_tables(path)
    parents = tables["item_history"].sort("era_from")

    assert parents.height == 2
    assert parents.get_column("cost").to_list() == [500, 800]
    assert parents.get_column("client_version").to_list() == [100, 200]
    assert parents.schema["era_from"] == pl.Datetime("us", "UTC")


def test_item_parent_matches_item_asof(tmp_path):
    path = tmp_path / "item_history.parquet"
    history.write(path, ITEM_STATES)

    parents = unnest.item_tables(path)["item_history"]

    for row in parents.iter_rows(named=True):
        resolved = items.item_asof(7, row["era_from"], path=path)

        assert resolved is not None

        assert resolved.cost == row["cost"]


def test_item_components_fan_out_per_era(tmp_path):
    path = tmp_path / "item_history.parquet"
    history.write(path, ITEM_STATES)

    comps = unnest.item_tables(path)["item_component_history"]

    assert comps.height == 3
    assert sorted(comps.filter(pl.col("client_version") == 200)["position"].to_list()) == [0, 1]


def test_hero_stat_history_tracks_change(tmp_path):
    path = tmp_path / "hero_history.parquet"
    history.write(path, HERO_STATES)

    stats = unnest.hero_tables(path)["hero_stat_history"].sort("era_from")
    health = stats.filter(pl.col("stat") == "max_health")

    assert health.get_column("value").to_list() == [600.0, 650.0]

    level_up = unnest.hero_tables(path)["hero_level_up_history"]
    assert level_up.filter(pl.col("stat") == "tech_power")["per_level_value"].to_list() == [
        1.5,
        1.5,
    ]


def test_ability_property_merges_value_and_scaling(tmp_path):
    path = tmp_path / "ability_history.parquet"
    history.write(path, ABILITY_STATES)

    props = unnest.ability_tables(path)["ability_property_history"]
    row = props.filter(pl.col("ability_class") == "citadel_ability_x").row(0, named=True)

    assert row["value"] == 60.0
    assert row["scale_stat"] == "tech_power"
    assert row["scale"] == 1.0


def test_ability_upgrade_tier_is_one_based(tmp_path):
    path = tmp_path / "ability_history.parquet"
    history.write(path, ABILITY_STATES)

    upgrades = unnest.ability_tables(path)["ability_upgrade_history"]

    assert upgrades.height == 1
    assert upgrades.get_column("tier").to_list() == [1]
    assert upgrades.get_column("bonus").to_list() == [10.0]


def test_ability_weapon_only_for_guns(tmp_path):
    path = tmp_path / "ability_history.parquet"
    history.write(path, ABILITY_STATES)

    weapons = unnest.ability_tables(path)["ability_weapon_history"]

    assert weapons.height == 1
    assert weapons.get_column("ability_class").to_list() == ["citadel_weapon_x"]
    assert weapons.get_column("bullet_damage").to_list() == [10.0]
    assert weapons.get_column("clip_size").to_list() == [20.0]
    assert weapons.get_column("range").to_list() == [None]


def test_rank_table_flattens(tmp_path):
    path = tmp_path / "rank_history.parquet"
    history.write(path, RANK_STATES)

    ranks = unnest.rank_tables(path)["rank_history"]

    assert ranks.to_dicts()[0]["name"] == "Initiate"
    assert ranks.get_column("tier").to_list() == [1]


def test_statue_table_flattens_each_era(tmp_path):
    path = tmp_path / "statue_history.parquet"
    history.write(path, STATUE_STATES)

    table = unnest.statue_tables(path)["statue_history"].sort("era_from")

    assert list(table.columns) == list(schemas.TABLES["statue_history"])
    assert table.get_column("value").to_list() == [25.0, 20.0]
    assert table.get_column("buff").to_list() == ["hp", "hp"]
    assert table.get_column("level").to_list() == [2, 2]
    assert table.get_column("client_version").to_list() == [100, 200]


def test_missing_history_gives_empty_typed_frames(tmp_path):
    missing = tmp_path / "none.parquet"
    tables = unnest.item_tables(missing)

    for name in ("item_history", "item_component_history"):
        df = tables[name]
        assert df.height == 0
        assert df.columns == list(schemas.TABLES[name])
