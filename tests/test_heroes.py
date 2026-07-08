import dataclasses
import json

import pytest

from deadlock_matches import heroes


def test_hero_map_loads_real_file():
    m = heroes.hero_map()

    assert m[52].name == "Mirage"
    assert m[52].class_name == "hero_mirage"
    assert all(isinstance(k, int) for k in m)


def test_hero_name_known_and_unknown():
    assert heroes.hero_name(52) == "Mirage"
    assert heroes.hero_name(999999) == "id999999"


def test_from_record_ignores_extra_keys():
    rec = {
        "id": 1,
        "name": "Infernus",
        "class_name": "hero_inferno",
        "tags": ["Burst"],
        "something_unmodeled": {"a": 1},
    }

    h = heroes.Hero.from_record(rec)

    assert h.name == "Infernus"
    assert h.tags == ("Burst",)
    assert h.hero_type is None
    assert h.disabled is False


def test_custom_path(tmp_path):
    p = tmp_path / "h.json"
    p.write_text(json.dumps([{"id": 7, "name": "Wraith", "class_name": "hero_wraith"}]))

    assert heroes.hero_name(7, p) == "Wraith"


def test_hero_is_frozen():
    h = heroes.hero_map()[52]

    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(h, "name", "test")


SCALING_REC = {
    "id": 52,
    "name": "Mirage",
    "class_name": "hero_mirage",
    "stats": {"max_health": 730},
    "level_up": {"base_health_from_level": 45.0, "tech_power": 1.1},
    "levels": [
        {"level": 1, "required_souls": 0, "standard_upgrade": False, "currencies": []},
        {
            "level": 2,
            "required_souls": 200,
            "standard_upgrade": True,
            "currencies": ["ability_points"],
        },
        {"level": 3, "required_souls": 500, "standard_upgrade": True, "currencies": []},
    ],
    "cost_bonuses": {
        "spirit": [{"souls": 800, "bonus": 7.0}, {"souls": 4800, "bonus": 38.0}],
    },
}


def test_level_for_souls():
    h = heroes.Hero.from_record(SCALING_REC)

    assert h.level_for_souls(0) == 1
    assert h.level_for_souls(199) == 1
    assert h.level_for_souls(200) == 2
    assert h.level_for_souls(9999) == 3


def test_base_health_scales_with_standard_levels():
    h = heroes.Hero.from_record(SCALING_REC)

    assert h.base_health(1) == 730.0
    assert h.base_health(2) == 775.0
    assert h.base_health(3) == 820.0


def test_spirit_power_from_boons():
    h = heroes.Hero.from_record(SCALING_REC)

    assert h.spirit_power(1) == 0.0
    assert h.spirit_power(3) == pytest.approx(2.2)


def test_scaling_defaults_when_snapshot_lacks_levels():
    h = heroes.Hero.from_record({"id": 7, "name": "Wraith", "class_name": "hero_wraith"})

    assert h.levels == ()
    assert h.level_for_souls(50000) == 0
    assert h.base_health(36) == 0.0
    assert h.spirit_power(36) == 0.0


def test_investment_bonus_steps():
    h = heroes.Hero.from_record(SCALING_REC)

    assert h.investment_bonus("spirit", 0) == 0.0
    assert h.investment_bonus("spirit", 800) == 7.0
    assert h.investment_bonus("spirit", 4799) == 7.0
    assert h.investment_bonus("spirit", 4800) == 38.0
    assert h.investment_bonus("weapon", 99999) == 0.0


def test_real_snapshot_carries_level_scaling():
    h = heroes.hero_map()[52]

    assert h.level_up["base_health_from_level"] > 0
    assert len(h.levels) == 36
    assert h.levels[-1].required_souls > h.levels[0].required_souls
    assert h.base_health(36) > h.stats["max_health"]
    assert h.purchase_bonuses["vitality"][0]["stat"] == "base_health_percent"
    assert h.investment_bonus("spirit", 4800) > h.investment_bonus("spirit", 4799)


BOON_REC = {
    "id": 52,
    "name": "Mirage",
    "class_name": "hero_mirage",
    "stats": {"max_health": 730, "light_melee_damage": 50.0, "heavy_melee_damage": 116},
    "level_up": {
        "base_health_from_level": 45.0,
        "tech_power": 1.1,
        "base_bullet_damage_from_level": 0.3,
        "base_melee_damage_from_level": 1.58,
    },
    "levels": [
        {
            "level": 1,
            "required_souls": 0,
            "standard_upgrade": False,
            "currencies": ["ability_unlocks"],
        },
        {
            "level": 2,
            "required_souls": 200,
            "standard_upgrade": True,
            "currencies": ["ability_points"],
        },
        {
            "level": 3,
            "required_souls": 500,
            "standard_upgrade": True,
            "currencies": ["ability_unlocks"],
        },
        {
            "level": 4,
            "required_souls": 900,
            "standard_upgrade": True,
            "currencies": ["ability_points"],
        },
    ],
}


def test_ability_currencies_by_level():
    h = heroes.Hero.from_record(BOON_REC)

    assert h.ability_points(1) == 0
    assert h.ability_points(2) == 1
    assert h.ability_points(4) == 2
    assert h.ability_unlocks(1) == 1
    assert h.ability_unlocks(4) == 2


def test_bullet_damage_bonus():
    h = heroes.Hero.from_record(BOON_REC)

    assert h.bullet_damage_bonus(1) == 0.0
    assert h.bullet_damage_bonus(4) == pytest.approx(0.9)


def test_melee_damage_keeps_heavy_ratio():
    h = heroes.Hero.from_record(BOON_REC)
    light, heavy = h.melee_damage(4)

    assert light == pytest.approx(50 + 3 * 1.58)
    assert heavy == pytest.approx(116 + 3 * 1.58 * 2.32)


def test_melee_damage_without_stats():
    h = heroes.Hero.from_record({"id": 7, "name": "Wraith", "class_name": "hero_wraith"})

    assert h.melee_damage(10) == (0.0, 0.0)


def test_boon_stats_and_stats_at():
    h = heroes.Hero.from_record(BOON_REC)
    at = h.stats_at(900)

    assert at["souls"] == 900
    assert at["level"] == 4
    assert at["max_health"] == 730 + 3 * 45
    assert at["spirit_power"] == pytest.approx(3.3)
    assert at["ability_points"] == 2
    assert at["ability_unlocks"] == 2
    assert at["light_melee_damage"] == pytest.approx(54.74)
    assert at == {"souls": 900, **h.boon_stats(4)}
