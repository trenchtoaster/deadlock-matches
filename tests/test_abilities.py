import datetime as dt
import re

import pytest

from deadlock_matches import abilities, history


def _ability_history(path, first, second):
    def era(damage):
        return {
            "ability_slash": {
                "id": 1,
                "name": "Slash",
                "class_name": "ability_slash",
                "hero": 52,
                "kind": "ability",
                "properties": {"damage": damage},
            }
        }

    history.write(
        path,
        [
            {"from": "2026-01-01T00:00:00", "build": 1, "records": era(first)},
            {"from": "2026-07-01T00:00:00", "build": 2, "records": era(second)},
        ],
    )


def test_ability_asof_picks_the_era(tmp_path):
    path = tmp_path / "ability_history.parquet"
    _ability_history(path, 60, 75)

    assert abilities.ability_asof("ability_slash", dt.date(2026, 6, 20), path).properties["damage"] == 60
    assert abilities.ability_asof("ability_slash", dt.date(2026, 7, 2), path).properties["damage"] == 75


def test_ability_asof_without_history_falls_back_to_bundled(tmp_path):
    real = next(iter(abilities.ability_map()))
    missing = tmp_path / "none.parquet"

    assert abilities.ability_asof(real, dt.date(2026, 7, 2), missing).class_name == real
    assert abilities.ability_asof("no_such_class", dt.date(2026, 7, 2), missing) is None


def test_ability_map_loads_real_file():
    m = abilities.ability_map()

    assert m["mirage_tornado"].name == "Dust Devil"
    assert m["mirage_fire_beetles"].name == "Fire Scarabs"
    assert m["mirage_sand_phantom"].hero == 52


def test_label_resolves_gun():
    assert abilities.label("citadel_weapon_mirage_set") == "Promises Kept"


def test_label_falls_back_to_item():
    assert abilities.label("upgrade_escalating_exposure") == "Escalating Exposure"


def test_label_passthrough_for_engine_sources():
    assert abilities.label("Bullet") == "Bullet"
    assert abilities.label("no_such_class") == "no_such_class"


def test_label_crit_suffix():
    assert abilities.label("citadel_weapon_mirage_set_crit") == "Promises Kept (crit)"
    assert abilities.label("no_such_class_crit") == "no_such_class_crit"


def test_from_record_defaults():
    a = abilities.Ability.from_record({"id": 1, "name": "X", "class_name": "x"})

    assert a.hero is None
    assert a.kind == "ability"
    assert a.properties == {}
    assert a.upgrades == ()
    assert a.tier_descriptions == ()


TUNED = abilities.Ability.from_record(
    {
        "id": 1,
        "name": "X",
        "class_name": "x",
        "properties": {"damage": 65, "radius": 4},
        "scaling": {"damage": {"stat": "tech_power", "scale": 0.3}},
        "upgrades": [
            [{"property": "damage", "bonus": 60}],
            [{"property": "ability_cooldown", "bonus": -12}],
            [{"property": "damage", "bonus": 1.0, "type": "add_to_scale", "stat": "tech_power"}],
        ],
    }
)


def test_stat_applies_flat_bonuses_by_tier():
    assert TUNED.stat("damage") == 65
    assert TUNED.stat("damage", 1) == 125
    assert TUNED.stat("ability_cooldown", 1) == 0
    assert TUNED.stat("ability_cooldown", 2) == -12


def test_stat_ignores_scale_upgrades():
    assert TUNED.stat("damage", 3) == TUNED.stat("damage", 1)


def test_spirit_scale_by_tier():
    assert TUNED.spirit_scale("damage") == 0.3
    assert TUNED.spirit_scale("damage", 2) == 0.3
    assert TUNED.spirit_scale("damage", 3) == 1.3
    assert TUNED.spirit_scale("radius", 3) == 0.0


def test_multiply_upgrades():
    a = abilities.Ability.from_record(
        {
            "id": 2,
            "name": "Y",
            "class_name": "y",
            "properties": {"damage": 10},
            "scaling": {"damage": {"stat": "tech_power", "scale": 1.0}},
            "upgrades": [
                [{"property": "damage", "bonus": 2, "type": "multiply_base"}],
                [{"property": "damage", "bonus": 1.5, "type": "multiply_scale"}],
            ],
        }
    )

    assert a.stat("damage", 1) == 20
    assert a.stat("damage", 2) == 20
    assert a.spirit_scale("damage", 2) == 1.5


def test_spirit_scale_skips_other_stats():
    a = abilities.Ability.from_record(
        {
            "id": 3,
            "name": "Z",
            "class_name": "z",
            "properties": {"damage": 50},
            "scaling": {"damage": {"stat": "light_melee_damage", "scale": 1.0}},
            "upgrades": [[{"property": "damage", "bonus": 1.0, "type": "add_to_scale"}]],
        }
    )

    assert a.spirit_scale("damage", 1) == 0.0


def test_real_snapshot_carries_tuning():
    tornado = abilities.ability_map()["mirage_tornado"]

    assert tornado.properties["damage"] > 0
    assert tornado.scaling["damage"]["stat"] == "tech_power"
    assert len(tornado.upgrades) == 3
    assert len(tornado.tier_descriptions) == 3
    assert all(tornado.tier_descriptions)
    assert tornado.description
    assert tornado.stat("damage", 1) > tornado.stat("damage")


def test_hero_gun():
    gun = abilities.hero_gun(52)

    assert gun is not None
    assert gun.name == "Promises Kept"
    assert gun.weapon["bullet_damage"] > 0
    assert abilities.hero_gun(999999) is None


def test_for_hero():
    names = {a.name for a in abilities.for_hero(52)}

    assert "Dust Devil" in names
    assert "Melee" in names


def test_ability_by_name():
    found = abilities.ability_by_name("dust devil")

    assert found is not None
    assert found.class_name == "mirage_tornado"
    assert abilities.ability_by_name("no such thing") is None


def test_ability_by_name_ambiguous_raises():
    with pytest.raises(ValueError, match="several heroes"):
        abilities.ability_by_name("Melee")

    melee = abilities.ability_by_name("Melee", hero_id=52)

    assert melee is not None
    assert melee.class_name == "ability_melee_mirage"


def test_snapshot_upgrade_types_are_all_handled():
    known = {"add_to_base", "multiply_base", "add_to_scale", "multiply_scale"}

    for a in abilities.ability_map().values():
        for tier in a.upgrades:
            for up in tier:
                assert up.get("type", "add_to_base") in known, (a.class_name, up)
                assert isinstance(up["bonus"], int | float), (a.class_name, up)


SPLIT_ACRONYM = re.compile(r"(?:^|_)[a-z0-9](?:_[a-z0-9])+(?:_|$)")


def test_snapshot_keys_keep_acronyms_together():
    for a in abilities.ability_map().values():
        for key in (*a.properties, *a.scaling):
            assert not SPLIT_ACRONYM.search(key), (a.class_name, key)
            assert "__" not in key, (a.class_name, key)


def test_snapshot_values_are_numeric():
    for a in abilities.ability_map().values():
        for key, value in a.properties.items():
            assert isinstance(value, int | float), (a.class_name, key, value)

        for info in a.scaling.values():
            assert isinstance(info["scale"], int | float), (a.class_name, info)

        for value in a.weapon.values():
            assert isinstance(value, int | float), (a.class_name, value)


def test_snapshot_tier_descriptions_align_with_upgrades():
    for a in abilities.ability_map().values():
        if a.kind == "ability":
            assert len(a.tier_descriptions) == len(a.upgrades), a.class_name


def test_tier_math_runs_for_every_snapshot_record():
    for a in abilities.ability_map().values():
        for prop in {*a.properties, *a.scaling}:
            for tier in range(len(a.upgrades) + 1):
                assert isinstance(a.stat(prop, tier), float)
                assert isinstance(a.scaling_at(prop, tier), dict)
