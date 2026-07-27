from types import SimpleNamespace

import polars as pl

from deadlock_matches import queries
from deadlock_matches.assets import abilities, accolades, heroes, items


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
