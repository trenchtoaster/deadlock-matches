from types import SimpleNamespace

import polars as pl

from deadlock_matches import queries
from deadlock_matches.assets import abilities, accolades, heroes, items, statues
from deadlock_matches.extract import pb


def test_hero_name_follows_current_assets_without_changing_source(monkeypatch):
    source = pl.LazyFrame({"hero_id": [52, 999]})

    monkeypatch.setattr(
        heroes,
        "hero_map",
        lambda: {52: SimpleNamespace(name="Old Name")},
    )
    old = source.select(queries.hero_name().alias("hero")).collect()

    monkeypatch.setattr(
        heroes,
        "hero_map",
        lambda: {52: SimpleNamespace(name="New Name")},
    )
    new = source.select(queries.hero_name().alias("hero")).collect()

    assert old.get_column("hero").to_list() == ["Old Name", "id999"]
    assert new.get_column("hero").to_list() == ["New Name", "id999"]


def test_damage_source_name_labels_unknown_ability(monkeypatch):
    monkeypatch.setattr(abilities, "ability_map", lambda path=None: {})
    monkeypatch.setattr(items, "item_map", lambda path=None: {})

    resolved = (
        pl.LazyFrame({"source_class": ["UnknownAbility"]})
        .select(queries.damage_source_name().alias("source_name"))
        .collect()
        .get_column("source_name")
        .to_list()
    )

    assert resolved == ["Unknown ability"]


def test_damage_source_name_matches_the_label_helper_on_crit_classes(monkeypatch):
    named = SimpleNamespace(id=7, class_name="citadel_weapon_named", name="Promises Kept")
    unnamed = SimpleNamespace(
        id=8,
        class_name="citadel_weapon_unnamed",
        name="citadel_weapon_unnamed",
    )
    by_class = {a.class_name: a for a in (named, unnamed)}
    monkeypatch.setattr(abilities, "ability_map", lambda path=None: by_class)
    monkeypatch.setattr(items, "item_map", lambda path=None: {})
    monkeypatch.setattr(items, "item_by_class_name", lambda *_: None)

    classes = [
        "citadel_weapon_named",
        "citadel_weapon_named_crit",
        "citadel_weapon_unnamed",
        "citadel_weapon_unnamed_crit",
        "engine_source_crit",
    ]
    resolved = (
        pl.LazyFrame({"source_class": classes})
        .select(queries.damage_source_name().alias("source_name"))
        .collect()
        .get_column("source_name")
        .to_list()
    )

    assert resolved == [abilities.label(c) for c in classes]
    assert resolved == [
        "Promises Kept",
        "Promises Kept (crit)",
        "citadel_weapon_unnamed",
        "citadel_weapon_unnamed_crit",
        "engine_source_crit",
    ]


def test_damage_source_name_follows_current_assets_after_aggregation(monkeypatch):
    source = pl.LazyFrame(
        {
            "source_class": ["ability_test", "ability_test", "unknown"],
            "damage": [10, 20, 5],
        }
    )
    monkeypatch.setattr(
        abilities,
        "ability_map",
        lambda: {
            "ability_test": SimpleNamespace(
                id=7,
                class_name="ability_test",
                name="Old Name",
            )
        },
    )
    monkeypatch.setattr(items, "item_map", dict)

    old = (
        source.group_by("source_class")
        .agg(pl.col("damage").sum())
        .with_columns(queries.damage_source_name().alias("source_name"))
        .sort("source_class")
        .collect()
    )

    monkeypatch.setattr(
        abilities,
        "ability_map",
        lambda: {
            "ability_test": SimpleNamespace(
                id=7,
                class_name="ability_test",
                name="New Name",
            )
        },
    )
    new = (
        source.group_by("source_class")
        .agg(pl.col("damage").sum())
        .with_columns(queries.damage_source_name().alias("source_name"))
        .sort("source_class")
        .collect()
    )

    assert old.get_column("source_name").to_list() == ["Old Name", "unknown"]
    assert new.get_column("source_name").to_list() == ["New Name", "unknown"]
    assert new.get_column("damage").to_list() == [30, 5]


def test_id_labels_follow_current_assets(monkeypatch):
    monkeypatch.setattr(
        abilities,
        "ability_map",
        lambda: {
            "ability_test": SimpleNamespace(
                id=7,
                class_name="ability_test",
                name="Ability Name",
            )
        },
    )
    monkeypatch.setattr(
        items,
        "item_map",
        lambda: {
            8: SimpleNamespace(
                class_name="upgrade_test",
                name="Item Name",
            )
        },
    )
    monkeypatch.setattr(
        accolades,
        "accolade_map",
        lambda: {9: SimpleNamespace(class_name="headshot_damage")},
    )
    source = pl.LazyFrame({"ability_id": [7, 8, 99]})

    stacks = queries.with_stack_labels(source).collect()
    imbued = (
        pl.LazyFrame({"imbued_ability_id": [7, 99]})
        .select(queries.imbued_ability_name().alias("name"))
        .collect()
    )
    accolade = (
        pl.LazyFrame({"accolade_id": [9, 99]})
        .select(queries.accolade_name().alias("name"))
        .collect()
    )

    assert stacks.get_column("class_name").to_list() == [
        "ability_test",
        "upgrade_test",
        None,
    ]
    assert stacks.get_column("name").to_list() == ["Ability Name", "Item Name", None]
    assert imbued.get_column("name").to_list() == ["Ability Name", None]
    assert accolade.get_column("name").to_list() == ["headshot_damage", None]


def test_soul_source_name_covers_every_protobuf_value():
    descriptor = pb.CMsgMatchMetaDataContents.DESCRIPTOR

    assert descriptor is not None

    enum = descriptor.enum_types_by_name["EGoldSource"]
    ids = [v.number for v in enum.values]

    resolved = (
        pl.LazyFrame({"source": [*ids, 999]})
        .select(queries.soul_source_name().alias("source_name"))
        .collect()
        .get_column("source_name")
        .to_list()
    )

    assert resolved[:-1] == [queries.labels.SOUL_SOURCE_NAMES[i] for i in ids]
    assert resolved[-1] == "999"


def test_lane_name_resolves_engine_ids():
    resolved = (
        pl.LazyFrame({"assigned_lane": [1, 4, 6, 2, None]})
        .select(queries.lane_name().alias("lane"))
        .collect()
        .get_column("lane")
        .to_list()
    )

    assert resolved == ["yellow", "blue", "green", None, None]


def test_objective_labels_align_with_the_protobuf_enum():
    enum = pb.DESCRIPTOR.pool.FindEnumTypeByName("ECitadelTeamObjective")
    by_id = {v.number: v.name for v in enum.values}

    for objective_id, name in queries.labels.OBJECTIVE_NAMES.items():
        wire = by_id[objective_id]

        if name == "Guardian":
            assert "Tier1" in wire
        elif name == "Walker":
            assert "Tier2" in wire
        elif name == "Base Guardians":
            assert "BarrackBoss" in wire
        elif name == "Shrine":
            assert "ShieldGenerator" in wire
        elif name == "Patron":
            assert wire.endswith("Titan")
        else:
            assert name == "Weakened Patron"
            assert wire.endswith("Core")

    lanes = queries.labels.OBJECTIVE_LANE_IDS

    for objective_id, lane in lanes.items():
        assert by_id[objective_id].endswith(f"Lane{lane}")

    assert set(queries.labels.OBJECTIVE_NAMES) == set(by_id)


def test_objective_labels_resolve_names_and_lanes():
    frame = pl.LazyFrame({"objective_id": [1, 5, 9, 0, 10, 13, 2, 99]})
    labeled = queries.with_objective_labels(frame).collect()

    assert labeled.get_column("objective").to_list() == [
        "Guardian",
        "Walker",
        "Patron",
        "Weakened Patron",
        "Shrine",
        "Base Guardians",
        "Guardian",
        None,
    ]
    assert labeled.get_column("lane").to_list() == [
        "yellow",
        "yellow",
        None,
        None,
        None,
        None,
        None,
        None,
    ]


def test_buff_labels_mirror_parse_pickup():
    types = [
        "hp_permanent_pickup",
        "hp_permanent_pickup_lv2",
        "spirit_permanent_pickup_lv3",
        "gun_powerup_pickup",
        "something_else",
    ]
    labeled = queries.with_buff_labels(pl.LazyFrame({"type": types})).collect()
    expected = [statues.parse_pickup(t) for t in types]

    assert labeled.get_column("buff").to_list() == [b for b, _ in expected]
    assert labeled.get_column("level").to_list() == [lv for _, lv in expected]
    assert labeled.get_column("buff").to_list() == ["hp", "hp", "spirit", "gun", None]
    assert labeled.get_column("level").to_list() == [1, 2, 3, None, None]
