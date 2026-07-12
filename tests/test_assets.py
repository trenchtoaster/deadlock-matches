import datetime as dt
import email.message
import json
import urllib.error

import pytest

from deadlock_matches.assets import abilities, heroes, history, items, snapshots

HERO_REC = {
    "id": 52,
    "name": "Mirage",
    "class_name": "hero_mirage",
    "hero_type": "EHeroType_Ranged",
    "tags": ["Sustain"],
    "player_selectable": True,
    "disabled": False,
    "starting_stats": {
        "max_health": {"value": 600, "display_stat_name": "EMaxHealth"},
        "sprint_speed": {"value": 2.0, "display_stat_name": "ESprintSpeed"},
    },
    "standard_level_up_upgrades": {
        "MODIFIER_VALUE_BASE_HEALTH_FROM_LEVEL": 45.0,
        "MODIFIER_VALUE_TECH_POWER": 1.1,
        "MODIFIER_VALUE_TECH_RESIST": 0.0,
    },
    "level_info": {
        "1": {"bonus_currencies": ["EAbilityUnlocks"], "required_gold": 0},
        "2": {
            "use_standard_upgrade": True,
            "bonus_currencies": ["EAbilityPoints"],
            "required_gold": 200,
        },
        "10": {"use_standard_upgrade": True, "required_gold": 4100},
    },
    "purchase_bonuses": {
        "vitality": [{"value_type": "MODIFIER_VALUE_BASE_HEALTH_PERCENT", "tier": 1, "value": "7"}],
    },
    "cost_bonuses": {
        "spirit": [
            {"gold_threshold": 800, "bonus": 7.0, "percent_on_graph": 7.0},
            {"gold_threshold": 4800, "bonus": 38.0, "percent_on_graph": 9.0},
        ],
    },
    "scaling_stats": {
        "EBulletDamage": {"scaling_stat": "ETechPower", "scale": 0.022},
    },
    "images": {"portrait": "https://example.com/mirage.png"},
    "physics": {"footstep_sound_travel_distance_meters": 25},
}

ITEM_REC = {
    "id": 1,
    "name": "Improved Burst",
    "class_name": "upgrade_improved_burst",
    "cost": 3500,
    "item_slot_type": "spirit",
    "item_tier": 3,
    "is_active_item": False,
    "description": {
        "desc": 'Deal <svg width="12"><path d="M1 2"/></svg> bonus <b>Spirit</b> damage'
    },
    "component_items": ["upgrade_mystic_burst"],
    "shop_image": "burst.png",
    "properties": {
        "TechPower": {
            "value": "18",
            "css_class": "tech",
            "disable_value": "0",
            "label": "Spirit Power",
            "prefix": "{s:sign}",
        },
        "BonusHealth": {"value": 75, "disable_value": "0", "label": "Health", "prefix": "{s:sign}"},
        "BonusSprintSpeed": {
            "value": "1m",
            "disable_value": "0",
            "label": "Sprint Speed",
            "postfix": "m/s",
        },
        "MaxHealthLossPercent": {
            "value": "-13",
            "disable_value": "0",
            "label": "Max Health",
            "postfix": "%",
        },
        "SlowPercent": {
            "value": "20",
            "css_class": "slow",
            "disable_value": "0",
            "label": "Move Speed",
            "postfix": "%",
            "prefix": "-",
        },
        "AbilityCooldown": {"value": "0", "disable_value": "0", "label": "Cooldown"},
        "AbilityCharges": {"value": "-1", "disable_value": "-1"},
    },
    "tooltip_sections": [
        {
            "section_type": "innate",
            "section_attributes": [
                {"properties": ["TechPower", "BonusHealth"], "elevated_properties": []}
            ],
        },
        {
            "section_type": "passive",
            "section_attributes": [
                {
                    "loc_string": "Deal <b>bonus</b> damage",
                    "properties": ["BonusSprintSpeed", "SlowPercent"],
                    "important_properties": ["MaxHealthLossPercent"],
                }
            ],
        },
    ],
}


ACCOLADE_REC = {
    "class_name": "kills",
    "id": 1,
    "tracked_stat_name": "kills",
    "flavor_name": "Killer Instinct",
    "description": '<span class="StatValue">{stat_value}</span> kills',
    "threshold_type": "automatic",
}


def test_refresh_accolades_keeps_id_stat_and_flavor_name(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [ACCOLADE_REC])
    p = tmp_path / "accolades.json"

    assert snapshots.refresh_accolades(p) == 1

    rec = json.loads(p.read_text())[0]

    assert rec == {"id": 1, "class_name": "kills", "name": "Killer Instinct"}


STATUE_REC = {
    "class_name": "hp_permanent_pickup_lv2",
    "id": 5,
    "modifier": {
        "subclass": {
            "class_name": "modifier_permanent_pickup",
            "script_values": [{"value_type": "MODIFIER_VALUE_HEALTH_MAX", "value": 20.0}],
        }
    },
}

CRATE_REC = {
    "class_name": "gun_powerup_pickup",
    "id": 9,
    "modifier": {"subclass": {"class_name": "modifier_citadel_powerup_gun"}},
}


def test_refresh_statues_keeps_the_permanent_stat(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [STATUE_REC, CRATE_REC])
    p = tmp_path / "statues.json"

    assert snapshots.refresh_statues(p) == 1

    rec = json.loads(p.read_text())[0]

    assert rec == {
        "id": 5,
        "class_name": "hp_permanent_pickup_lv2",
        "stat": "health_max",
        "value": 20,
    }


def test_refresh_heroes_flattens_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [HERO_REC])
    p = tmp_path / "heroes.json"

    assert snapshots.refresh_heroes(p) == 1

    rec = json.loads(p.read_text())[0]

    assert rec["name"] == "Mirage"
    assert rec["stats"] == {"max_health": 600, "sprint_speed": 2.0}
    assert "images" not in rec
    assert "physics" not in rec


def test_refresh_heroes_keeps_level_scaling(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [HERO_REC])
    p = tmp_path / "heroes.json"

    snapshots.refresh_heroes(p)

    rec = json.loads(p.read_text())[0]

    assert rec["level_up"] == {"base_health_from_level": 45.0, "tech_power": 1.1}
    assert rec["levels"] == [
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
        {"level": 10, "required_souls": 4100, "standard_upgrade": True, "currencies": []},
    ]
    assert rec["purchase_bonuses"] == {
        "vitality": [{"tier": 1, "stat": "base_health_percent", "value": 7.0}]
    }
    assert rec["cost_bonuses"] == {
        "spirit": [{"souls": 800, "bonus": 7.0}, {"souls": 4800, "bonus": 38.0}]
    }
    assert rec["scaling_stats"] == {"bullet_damage": {"stat": "tech_power", "scale": 0.022}}


def test_item_properties_keep_stat_grants_only(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    snapshots.refresh_items(p)

    rec = json.loads(p.read_text())[0]

    assert rec["properties"] == {
        "tech_power": 18,
        "bonus_health": 75,
        "bonus_sprint_speed": "1m",
        "max_health_loss_percent": -13,
        "slow_percent": 20,
    }


def test_refresh_items_maps_api_field_names(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    assert snapshots.refresh_items(p) == 1

    rec = json.loads(p.read_text())[0]

    assert rec["slot"] == "spirit"
    assert rec["tier"] == 3
    assert rec["is_active"] is False
    assert rec["components"] == ["upgrade_mystic_burst"]
    assert "shop_image" not in rec


def test_refresh_items_keeps_labels_for_surviving_properties(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    snapshots.refresh_items(p)

    rec = json.loads(p.read_text())[0]

    assert rec["labels"]["tech_power"] == {"label": "Spirit Power", "signed": True}
    assert rec["labels"]["bonus_sprint_speed"] == {"label": "Sprint Speed", "postfix": "m/s"}
    assert rec["labels"]["slow_percent"] == {"label": "Move Speed", "postfix": "%", "prefix": "-"}
    assert "ability_cooldown" not in rec["labels"]
    assert "ability_charges" not in rec["labels"]


def test_refresh_items_flattens_tooltip_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    snapshots.refresh_items(p)

    rec = json.loads(p.read_text())[0]

    assert rec["sections"] == [
        {"section": "innate", "text": None, "properties": ["tech_power", "bonus_health"]},
        {
            "section": "passive",
            "text": "Deal bonus damage",
            "properties": ["max_health_loss_percent", "bonus_sprint_speed", "slow_percent"],
        },
    ]


def test_scaling_and_types_reads_spirit_damage_scaling():
    props = {
        "DotHealthPercent": {
            "value": "1.9",
            "css_class": "tech_damage",
            "scale_function": {
                "class_name": "scale_function_tech_damage",
                "specific_stat_scale_type": "ETechPower",
                "stat_scale": 0.005,
            },
        }
    }

    derived = snapshots._derive_properties(props, {"dot_health_percent"})

    assert derived["scaling"] == {"dot_health_percent": {"stat": "tech_power", "scale": 0.005}}
    assert derived["damage_types"] == {"dot_health_percent": "spirit"}


def test_scaling_and_types_recovers_missing_scale_type():
    props = {
        "MagicDamagePerBullet": {
            "value": "1",
            "css_class": "tech_damage",
            "scale_function": {
                "class_name": "scale_function_tech_damage",
                "specific_stat_scale_type": None,
                "stat_scale": 0.03,
            },
        }
    }

    derived = snapshots._derive_properties(props, {"magic_damage_per_bullet"})

    assert derived["scaling"] == {"magic_damage_per_bullet": {"stat": "tech_power", "scale": 0.03}}
    assert derived["damage_types"] == {"magic_damage_per_bullet": "spirit"}


def test_scaling_and_types_skips_damage_colored_stat_grants():
    props = {
        "BaseAttackDamagePercent": {"value": "15", "css_class": "bullet_damage"},
        "WeaponPowerPerStack": {"value": "7", "css_class": "bullet_damage"},
        "BonusFireRatePerHero": {"value": "4", "css_class": "bullet_damage"},
    }
    kept = {"base_attack_damage_percent", "weapon_power_per_stack", "bonus_fire_rate_per_hero"}

    derived = snapshots._derive_properties(props, kept)

    assert derived["scaling"] == {}
    assert derived["damage_types"] == {}


def test_scaling_and_types_keeps_named_damage_without_a_damage_function():
    props = {
        "HeadShotBonusDamage": {
            "value": "40",
            "css_class": "bullet_damage",
            "scale_function": {"class_name": "scale_function_single_stat", "stat_scale": 4.0},
        }
    }

    derived = snapshots._derive_properties(props, {"head_shot_bonus_damage"})

    assert derived["damage_types"] == {"head_shot_bonus_damage": "weapon"}


def test_scaling_and_types_skips_filtered_out_properties():
    props = {
        "MaxHealthDamage": {
            "value": "0",
            "css_class": "tech_damage",
            "scale_function": {"class_name": "scale_function_tech_damage", "stat_scale": 0.1},
        }
    }

    derived = snapshots._derive_properties(props, set())

    assert derived["damage_types"] == {}


def test_scaling_flags_custom_nonlinear_functions():
    props = {
        "MaxBonusBulletDamage": {
            "value": "5",
            "css_class": "tech_damage",
            "scale_function": {
                "class_name": "scale_function_kinetic_carbine_damage",
                "specific_stat_scale_type": "EWeaponPower",
                "stat_scale": 125.0,
            },
        }
    }

    derived = snapshots._derive_properties(props, {"max_bonus_bullet_damage"})

    assert derived["scaling"]["max_bonus_bullet_damage"] == {
        "stat": "weapon_power",
        "scale": 125.0,
        "linear": False,
    }


def test_derive_properties_buckets_scale_types():
    props = {
        "AbilityCooldown": {
            "value": "14",
            "css_class": "cooldown",
            "scale_function": {"specific_stat_scale_type": "EItemCooldown"},
        },
        "AbilityRange": {
            "value": "20",
            "scale_function": {"specific_stat_scale_type": "ETechRange"},
        },
    }

    derived = snapshots._derive_properties(props, {"ability_cooldown", "ability_range"})

    assert derived["scale_types"] == {
        "ability_cooldown": "item_cooldown",
        "ability_range": "tech_range",
    }
    assert derived["scaling"] == {}


def test_derive_properties_marks_negatives_and_conditionals():
    props = {
        "OutgoingDamagePenaltyPercent": {"value": "-14", "negative_attribute": True},
        "NonPlayerBonusWeaponPower": {"value": "25", "conditional": "against NPCs"},
    }
    kept = {"outgoing_damage_penalty_percent", "non_player_bonus_weapon_power"}

    derived = snapshots._derive_properties(props, kept)

    assert derived["negatives"] == ["outgoing_damage_penalty_percent"]
    assert derived["conditionals"] == {"non_player_bonus_weapon_power": "against NPCs"}


def test_derive_properties_limits_new_views_to_kept():
    props = {
        "AbilityCooldown": {
            "value": "0",
            "scale_function": {"specific_stat_scale_type": "EItemCooldown"},
        },
        "Downside": {"value": "0", "negative_attribute": True, "conditional": "vs NPCs"},
    }

    derived = snapshots._derive_properties(props, set())

    assert derived["scale_types"] == {}
    assert derived["negatives"] == []
    assert derived["conditionals"] == {}


def test_item_snapshot_keeps_card_fields():
    rec = {
        "id": 5,
        "name": "Compress Cooldown",
        "item_slot_type": "spirit",
        "item_tier": 2,
        "is_active_item": False,
        "activation": "passive",
        "shopable": True,
        "disabled": False,
        "imbue": "imbue_modifier_value",
        "description": "reduces cooldowns",
        "properties": {
            "AbilityCooldown": {
                "value": "14",
                "css_class": "cooldown",
                "scale_function": {"specific_stat_scale_type": "EItemCooldown"},
            },
            "OutgoingDamagePenaltyPercent": {"value": "-14", "negative_attribute": True},
        },
        "upgrades": [{"property_upgrades": [{"name": "BonusClipSizePercent", "bonus": "30"}]}],
    }

    snap = snapshots._item_snapshot(rec)

    assert snap["activation"] == "passive"
    assert snap["imbue"] == "imbue_modifier_value"
    assert snap["disabled"] is False
    assert snap["scale_types"] == {"ability_cooldown": "item_cooldown"}
    assert snap["negatives"] == ["outgoing_damage_penalty_percent"]
    assert snap["upgrades"] == [[{"property": "bonus_clip_size_percent", "bonus": 30}]]


def test_ability_snapshot_keeps_card_fields():
    rec = {
        "id": 7,
        "name": "Seismic Impact",
        "class_name": "hero_seismic",
        "hero": 1,
        "ability_type": "ultimate",
        "boss_damage_scale": 0.5,
        "behaviours": ["CITADEL_ABILITY_BEHAVIOR_PROJECTILE"],
        "description": {"desc": "boom"},
        "properties": {
            "AbilityCooldown": {
                "value": "110",
                "scale_function": {"specific_stat_scale_type": "ETechCooldown"},
            },
        },
    }

    snap = snapshots._ability_snapshot(rec, "ability")

    assert snap["ability_type"] == "ultimate"
    assert snap["boss_damage_scale"] == 0.5
    assert snap["behaviours"] == ["CITADEL_ABILITY_BEHAVIOR_PROJECTILE"]
    assert snap["scale_types"] == {"ability_cooldown": "tech_cooldown"}


def test_ability_snapshot_captures_damage_types():
    rec = {
        "id": 3,
        "name": "Djinns Mark",
        "class_name": "mirage_sand_phantom",
        "properties": {
            "ProcDamageBase": {
                "value": "35",
                "css_class": "tech_damage",
                "scale_function": {
                    "class_name": "scale_function_tech_damage",
                    "specific_stat_scale_type": "ETechPower",
                    "stat_scale": 0.35,
                },
            }
        },
    }

    snap = snapshots._ability_snapshot(rec, "ability")

    assert snap["scaling"] == {"proc_damage_base": {"stat": "tech_power", "scale": 0.35}}
    assert snap["damage_types"] == {"proc_damage_base": "spirit"}


def test_loaded_item_defaults_without_display_fields(tmp_path):
    p = tmp_path / "items.json"
    p.write_text(json.dumps([{"id": 3, "name": "Old"}]))

    it = items.item_map(p)[3]

    assert it.labels == {}
    assert it.sections == ()


def test_description_markup_stripped(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    snapshots.refresh_items(p)

    rec = json.loads(p.read_text())[0]

    assert rec["description"] == "Deal bonus Spirit damage"


def test_clean_text_handles_missing():
    assert snapshots._clean_text(None) is None
    assert snapshots._clean_text("") is None
    assert snapshots._clean_text("<b></b>") is None
    assert snapshots._clean_text("plain") == "plain"


def test_refresh_items_clears_lookup_caches(tmp_path, monkeypatch):
    p = tmp_path / "items.json"
    p.write_text(json.dumps([{"id": 9, "name": "Old Name"}]))

    assert items.item_name(9, p) == "Old Name"

    monkeypatch.setattr(
        snapshots.api, "get_json", lambda path, **kw: [dict(ITEM_REC, id=9, name="New Name")]
    )
    snapshots.refresh_items(p)

    assert items.item_name(9, p) == "New Name"


def test_refresh_heroes_clears_lookup_cache(tmp_path, monkeypatch):
    p = tmp_path / "heroes.json"
    p.write_text(json.dumps([{"id": 5, "name": "Old", "class_name": "hero_old"}]))

    assert heroes.hero_name(5, p) == "Old"

    monkeypatch.setattr(
        snapshots.api, "get_json", lambda path, **kw: [dict(HERO_REC, id=5, name="New")]
    )
    snapshots.refresh_heroes(p)

    assert heroes.hero_name(5, p) == "New"


def test_loaded_item_carries_description_and_components(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    snapshots.refresh_items(p)

    it = items.item_map(p)[1]

    assert it.description == "Deal bonus Spirit damage"
    assert it.components == ("upgrade_mystic_burst",)
    assert it.properties["tech_power"] == 18


def test_refresh_abilities_combines_kinds(tmp_path, monkeypatch):
    def fake(path, **kw):
        if "ability" in path:
            return [
                {
                    "id": 1,
                    "name": "Dust Devil",
                    "class_name": "mirage_tornado",
                    "hero": 52,
                    "image": "x.png",
                }
            ]
        return [
            {
                "id": 2,
                "name": "Promises Kept",
                "class_name": "citadel_weapon_mirage_set",
                "hero": 52,
                "weapon_info": {
                    "bullet_damage": 14.8,
                    "clip_size": 16,
                    "bullet_speed": 32600.0,
                },
            }
        ]

    monkeypatch.setattr(snapshots.api, "get_json", fake)
    p = tmp_path / "abilities.json"

    assert snapshots.refresh_abilities(p) == 2

    recs = json.loads(p.read_text())

    assert [r["kind"] for r in recs] == ["ability", "weapon"]
    assert "image" not in recs[0]
    assert "weapon" not in recs[0]
    assert recs[1]["weapon"] == {"bullet_damage": 14.8, "clip_size": 16, "bullet_speed": 32600.0}


def test_refresh_abilities_clears_cache(tmp_path, monkeypatch):
    p = tmp_path / "abilities.json"
    p.write_text(json.dumps([{"id": 1, "name": "Old", "class_name": "x"}]))

    assert abilities.ability_map(p)["x"].name == "Old"

    monkeypatch.setattr(
        snapshots.api,
        "get_json",
        lambda path, **kw: [{"id": 1, "name": "New", "class_name": "x", "hero": 52}],
    )
    snapshots.refresh_abilities(p)

    assert abilities.ability_map(p)["x"].name == "New"


def test_loaded_hero_carries_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.api, "get_json", lambda path, **kw: [HERO_REC])
    p = tmp_path / "heroes.json"

    snapshots.refresh_heroes(p)

    h = heroes.hero_map(p)[52]

    assert h.stats["max_health"] == 600
    assert h.scaling_stats == {"bullet_damage": {"stat": "tech_power", "scale": 0.022}}


ABILITY_REC = {
    "id": 3,
    "name": "Dust Devil",
    "class_name": "mirage_tornado",
    "hero": 52,
    "description": {
        "desc": "Become a <b>whirlwind</b> , damaging enemies .",
        "t1_desc": '<span class="highlight">+60</span> Damage',
        "t2_desc": '<br><span class="highlight">-12s</span> Cooldown',
    },
    "properties": {
        "Damage": {
            "value": 65.0,
            "scale_function": {"specific_stat_scale_type": "ETechPower", "stat_scale": 0.3},
        },
        "AbilityCastRange": {"value": "20m", "disable_value": "0"},
        "AbilityCastDelay": {"value": "0", "disable_value": "0"},
        "AbilityCharges": {"value": "-1", "disable_value": "-1"},
        "SpecialText": {"value": "whirlwind"},
    },
    "upgrades": [
        {"property_upgrades": [{"name": "Damage", "bonus": "60"}]},
        {"property_upgrades": [{"name": "AbilityCooldown", "bonus": "-12"}]},
        {
            "property_upgrades": [
                {"name": "RecastWindow", "bonus": "6m"},
                {
                    "name": "Damage",
                    "bonus": 1.0,
                    "scale_stat_filter": "ETechPower",
                    "upgrade_type": "EAddToScale",
                },
                {"name": "OddOne", "bonus": "special"},
            ]
        },
    ],
}


def test_measure_parses_unit_strings():
    assert snapshots._measure("20m") == 20
    assert snapshots._measure("0.2s") == 0.2
    assert snapshots._measure("-35m") == -35
    assert snapshots._measure(".3m") == 0.3
    assert snapshots._measure("1.28") == 1.28
    assert snapshots._measure(36.0) == 36
    assert snapshots._measure("whirlwind") == "whirlwind"


def test_refresh_abilities_keeps_tuning_numbers(tmp_path, monkeypatch):
    monkeypatch.setattr(
        snapshots.api, "get_json", lambda path, **kw: [ABILITY_REC] if "ability" in path else []
    )
    p = tmp_path / "abilities.json"

    snapshots.refresh_abilities(p)

    rec = json.loads(p.read_text())[0]

    assert rec["description"] == "Become a whirlwind, damaging enemies."
    assert rec["tier_descriptions"] == ["+60 Damage", "-12s Cooldown", None]
    assert rec["properties"] == {"damage": 65, "ability_cast_range": 20}
    assert rec["scaling"] == {"damage": {"stat": "tech_power", "scale": 0.3}}
    assert rec["upgrades"] == [
        [{"property": "damage", "bonus": 60}],
        [{"property": "ability_cooldown", "bonus": -12}],
        [
            {"property": "recast_window", "bonus": 6},
            {"property": "damage", "bonus": 1, "type": "add_to_scale", "stat": "tech_power"},
        ],
    ]


def test_weapon_records_skip_ability_fields(tmp_path, monkeypatch):
    weapon = {
        "id": 4,
        "name": "Promises Kept",
        "class_name": "citadel_weapon_mirage_set",
        "hero": 52,
        "weapon_info": {"bullet_damage": 14.8},
        "properties": {"Damage": {"value": 10}},
    }
    monkeypatch.setattr(
        snapshots.api, "get_json", lambda path, **kw: [weapon] if "weapon" in path else []
    )
    p = tmp_path / "abilities.json"

    snapshots.refresh_abilities(p)

    rec = json.loads(p.read_text())[0]

    assert rec["weapon"] == {"bullet_damage": 14.8}
    assert "properties" not in rec
    assert "upgrades" not in rec


def _item_recs(cost):
    """One upgrade record in the raw API shape at a given cost."""
    return [
        {
            "id": 10,
            "name": "Foo",
            "class_name": "upgrade_foo",
            "cost": cost,
            "item_slot_type": "weapon",
            "item_tier": 1,
        }
    ]


def _fake_assets(builds, items_at):
    """A get_json stand-in serving steam-info dates and per-build item records."""

    def get_json(path, **kw):
        if "steam-info/all" in path:
            return [{"client_version": b, "version_datetime": d} for b, d in builds.items()]

        if "items/by-type/upgrade" in path:
            return items_at[int(path.split("client_version=")[1])]

        raise AssertionError(path)

    return get_json


def test_client_version_dates_maps_build_to_datetime(monkeypatch):
    monkeypatch.setattr(
        snapshots.api,
        "get_json",
        lambda path, **kw: [{"client_version": 5, "version_datetime": "2026-01-05T00:00:00"}],
    )

    assert snapshots.client_version_dates() == {5: "2026-01-05T00:00:00"}


def test_build_item_history_finds_the_change_point(tmp_path, monkeypatch):

    from deadlock_matches.assets import items

    builds = {
        1: "2026-01-01T00:00:00",
        2: "2026-01-02T00:00:00",
        3: "2026-01-03T00:00:00",
        4: "2026-01-04T00:00:00",
        5: "2026-01-05T00:00:00",
    }
    items_at = {b: _item_recs(500 if b < 4 else 800) for b in builds}
    monkeypatch.setattr(snapshots.api, "get_json", _fake_assets(builds, items_at))

    path = tmp_path / "item_history.parquet"
    n = snapshots.build_item_history(start_date="2026-01-01", path=path)

    early = items.item_asof(10, dt.datetime(2026, 1, 2), path)
    late = items.item_asof(10, dt.datetime(2026, 1, 5), path)

    assert n == 2
    assert early is not None
    assert early.cost == 500
    assert late is not None
    assert late.cost == 800


def test_build_item_history_single_era_when_nothing_changes(tmp_path, monkeypatch):
    builds = {b: f"2026-01-0{b}T00:00:00" for b in (1, 2, 3)}
    monkeypatch.setattr(
        snapshots.api, "get_json", _fake_assets(builds, {b: _item_recs(500) for b in builds})
    )

    path = tmp_path / "item_history.parquet"
    n = snapshots.build_item_history(start_date="2026-01-01", path=path)

    assert n == 1


def test_build_item_history_captures_a_revert(tmp_path, monkeypatch):
    builds = {b: f"2026-01-0{b}T00:00:00" for b in (1, 2, 3)}
    items_at = {1: _item_recs(500), 2: _item_recs(800), 3: _item_recs(500)}
    monkeypatch.setattr(snapshots.api, "get_json", _fake_assets(builds, items_at))

    from deadlock_matches.assets import items

    path = tmp_path / "item_history.parquet"
    n = snapshots.build_item_history(start_date="2026-01-01", path=path)

    first = items.item_asof(10, dt.datetime(2026, 1, 1), path)
    second = items.item_asof(10, dt.datetime(2026, 1, 2), path)
    third = items.item_asof(10, dt.datetime(2026, 1, 3), path)

    assert n == 3
    assert first is not None
    assert first.cost == 500
    assert second is not None
    assert second.cost == 800
    assert third is not None
    assert third.cost == 500


def test_load_build_skips_a_persistent_failure(monkeypatch):
    monkeypatch.setattr(snapshots.time, "sleep", lambda *_: None)
    calls = []

    def load(build):
        calls.append(build)
        raise OSError("500")

    cache = {}

    assert snapshots._load_build(2, cache, load, tries=2) is None
    assert len(calls) == 2
    assert cache[2] is None


def test_load_build_skips_a_404_without_retrying(monkeypatch):
    monkeypatch.setattr(snapshots.time, "sleep", lambda *_: None)
    calls = []

    def load(build):
        calls.append(build)
        raise urllib.error.HTTPError("url", 404, "not found", email.message.Message(), None)

    assert snapshots._load_build(2, {}, load, tries=4) is None
    assert len(calls) == 1


def test_load_build_retries_a_transient_500(monkeypatch):
    monkeypatch.setattr(snapshots.time, "sleep", lambda *_: None)
    calls = []

    def load(build):
        calls.append(build)

        if len(calls) == 1:
            raise urllib.error.HTTPError("url", 500, "server error", email.message.Message(), None)

        return {"10": {"cost": 500}}

    assert snapshots._load_build(2, {}, load, tries=4) == {"10": {"cost": 500}}
    assert len(calls) == 2


def test_build_item_history_skips_a_build_the_api_cannot_serve(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.time, "sleep", lambda *_: None)
    builds = {b: f"2026-01-0{b}T00:00:00" for b in (1, 2, 3)}
    items_at = {1: _item_recs(500), 3: _item_recs(800)}

    def get_json(path, **kw):
        if "steam-info/all" in path:
            return [{"client_version": b, "version_datetime": d} for b, d in builds.items()]

        if "client_version=2" in path:
            raise urllib.error.HTTPError("url", 500, "server error", email.message.Message(), None)

        build = int(path.rsplit("=", 1)[1])

        return items_at[build]

    monkeypatch.setattr(snapshots.api, "get_json", get_json)

    seen = []
    path = tmp_path / "item_history.parquet"
    n = snapshots.build_item_history(
        start_date="2026-01-01", path=path, progress=lambda *a: seen.append(a)
    )

    early = items.item_asof(10, dt.datetime(2026, 1, 2), path)
    late = items.item_asof(10, dt.datetime(2026, 1, 3), path)

    assert n == 2
    assert early is not None
    assert early.cost == 500
    assert late is not None
    assert late.cost == 800
    assert seen[-1] == (3, 3, [2])


def test_build_history_refuses_to_write_when_every_build_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots.time, "sleep", lambda *_: None)
    builds = {1: "2026-01-01T00:00:00", 2: "2026-01-02T00:00:00"}
    monkeypatch.setattr(
        snapshots,
        "client_version_dates",
        lambda **kw: builds,
    )

    def dead(build):
        raise urllib.error.HTTPError("url", 404, "not found", email.message.Message(), None)

    path = tmp_path / "history.parquet"

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        snapshots.build_asset_history(dead, path)

    assert not path.exists()


def test_build_item_history_reports_progress_per_build(tmp_path, monkeypatch):
    builds = {b: f"2026-01-0{b}T00:00:00" for b in (1, 2, 3)}
    monkeypatch.setattr(
        snapshots.api, "get_json", _fake_assets(builds, {b: _item_recs(500) for b in builds})
    )

    seen = []
    snapshots.build_item_history(
        start_date="2026-01-01",
        path=tmp_path / "item_history.parquet",
        progress=lambda *a: seen.append(a),
    )

    assert seen == [(1, 3, []), (2, 3, []), (3, 3, [])]


def test_build_item_history_resumes_from_the_last_era(tmp_path, monkeypatch):
    path = tmp_path / "item_history.parquet"
    builds = {b: f"2026-01-0{b}T00:00:00" for b in (1, 2, 3)}
    items_at = {1: _item_recs(500), 2: _item_recs(500), 3: _item_recs(800)}
    monkeypatch.setattr(snapshots.api, "get_json", _fake_assets(builds, items_at))
    first = snapshots.build_item_history(start_date="2026-01-01", path=path)

    builds |= {4: "2026-01-04T00:00:00", 5: "2026-01-05T00:00:00"}
    items_at |= {4: _item_recs(800), 5: _item_recs(1000)}
    monkeypatch.setattr(snapshots.api, "get_json", _fake_assets(builds, items_at))

    seen = []
    n = snapshots.build_item_history(
        start_date="2026-01-01", path=path, progress=lambda *a: seen.append(a)
    )

    assert first == 2
    assert n == 3
    assert [done for done, _total, _skipped in seen] == [1, 2]
    assert {total for _done, total, _skipped in seen} == {2}

    early = items.item_asof(10, dt.datetime(2026, 1, 2), path)
    late = items.item_asof(10, dt.datetime(2026, 1, 5), path)

    assert early is not None
    assert early.cost == 500
    assert late is not None
    assert late.cost == 1000


def test_build_item_history_incremental_no_change_leaves_the_file(tmp_path, monkeypatch):
    path = tmp_path / "item_history.parquet"
    builds = {b: f"2026-01-0{b}T00:00:00" for b in (1, 2, 3)}
    monkeypatch.setattr(
        snapshots.api, "get_json", _fake_assets(builds, {b: _item_recs(500) for b in builds})
    )
    snapshots.build_item_history(start_date="2026-01-01", path=path)
    mtime = path.stat().st_mtime_ns

    builds |= {4: "2026-01-04T00:00:00"}
    monkeypatch.setattr(
        snapshots.api, "get_json", _fake_assets(builds, {b: _item_recs(500) for b in builds})
    )
    n = snapshots.build_item_history(start_date="2026-01-01", path=path)

    assert n == 1
    assert path.stat().st_mtime_ns == mtime


def test_build_item_history_incremental_captures_a_revert_in_new_builds(tmp_path, monkeypatch):
    path = tmp_path / "item_history.parquet"
    builds = {b: f"2026-01-0{b}T00:00:00" for b in (1, 2, 3)}
    monkeypatch.setattr(
        snapshots.api, "get_json", _fake_assets(builds, {b: _item_recs(500) for b in builds})
    )
    snapshots.build_item_history(start_date="2026-01-01", path=path)

    builds |= {4: "2026-01-04T00:00:00", 5: "2026-01-05T00:00:00"}
    items_at = {1: _item_recs(500), 2: _item_recs(500), 3: _item_recs(500)}
    items_at |= {4: _item_recs(800), 5: _item_recs(500)}
    monkeypatch.setattr(snapshots.api, "get_json", _fake_assets(builds, items_at))

    n = snapshots.build_item_history(start_date="2026-01-01", path=path)

    fourth = items.item_asof(10, dt.datetime(2026, 1, 4), path)
    fifth = items.item_asof(10, dt.datetime(2026, 1, 5), path)

    assert n == 3
    assert fourth is not None
    assert fourth.cost == 800
    assert fifth is not None
    assert fifth.cost == 500


def test_build_item_history_full_rescans_an_old_build_correction(tmp_path, monkeypatch):
    path = tmp_path / "item_history.parquet"
    builds = {b: f"2026-01-0{b}T00:00:00" for b in (1, 2, 3)}
    items_at = {1: _item_recs(500), 2: _item_recs(500), 3: _item_recs(800)}
    monkeypatch.setattr(snapshots.api, "get_json", _fake_assets(builds, items_at))
    snapshots.build_item_history(start_date="2026-01-01", path=path)

    corrected = {1: _item_recs(500), 2: _item_recs(999), 3: _item_recs(800)}
    monkeypatch.setattr(snapshots.api, "get_json", _fake_assets(builds, corrected))

    incremental = snapshots.build_item_history(start_date="2026-01-01", path=path)
    full = snapshots.build_item_history(start_date="2026-01-01", path=path, full=True)

    assert incremental == 2
    assert full == 3


def _stub_history(tmp_path, monkeypatch, live, stored):
    """Point one LIVE_HISTORY_CHECKS entry at a json snapshot and parquet built from these records."""
    json_path = tmp_path / "items.json"
    hist_path = tmp_path / "item_history.parquet"
    json_path.write_text(json.dumps(live), encoding="utf-8")

    if stored is not None:
        history.write(
            hist_path,
            [{"from": "2026-06-30T10:07:00", "build": 6601, "records": stored}],
        )

    monkeypatch.setattr(snapshots, "LIVE_HISTORY_CHECKS", (("items", json_path, hist_path, "id"),))


def test_history_lags_flags_a_trailing_type(tmp_path, monkeypatch):
    _stub_history(tmp_path, monkeypatch, [{"id": 10, "cost": 500}], {"10": {"id": 10, "cost": 800}})

    assert snapshots.history_lags() == [("items", "2026-06-30", 6601)]


def test_history_lags_quiet_when_live_matches_history(tmp_path, monkeypatch):
    _stub_history(tmp_path, monkeypatch, [{"id": 10, "cost": 800}], {"10": {"id": 10, "cost": 800}})

    assert snapshots.history_lags() == []


def test_history_lags_skips_a_type_without_history(tmp_path, monkeypatch):
    _stub_history(tmp_path, monkeypatch, [{"id": 10, "cost": 500}], None)

    assert snapshots.history_lags() == []
