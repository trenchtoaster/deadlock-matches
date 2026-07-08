import datetime as dt
import json

from deadlock_matches import abilities, assets, heroes, items

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
                    "properties": ["BonusSprintSpeed"],
                    "important_properties": ["MaxHealthLossPercent"],
                }
            ],
        },
    ],
}


def test_refresh_heroes_flattens_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [HERO_REC])
    p = tmp_path / "heroes.json"

    assert assets.refresh_heroes(p) == 1

    rec = json.loads(p.read_text())[0]

    assert rec["name"] == "Mirage"
    assert rec["stats"] == {"max_health": 600, "sprint_speed": 2.0}
    assert "images" not in rec
    assert "physics" not in rec


def test_refresh_heroes_keeps_level_scaling(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [HERO_REC])
    p = tmp_path / "heroes.json"

    assets.refresh_heroes(p)

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
    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    assets.refresh_items(p)

    rec = json.loads(p.read_text())[0]

    assert rec["properties"] == {
        "tech_power": 18,
        "bonus_health": 75,
        "bonus_sprint_speed": "1m",
        "max_health_loss_percent": -13,
    }


def test_refresh_items_maps_api_field_names(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    assert assets.refresh_items(p) == 1

    rec = json.loads(p.read_text())[0]

    assert rec["slot"] == "spirit"
    assert rec["tier"] == 3
    assert rec["is_active"] is False
    assert rec["components"] == ["upgrade_mystic_burst"]
    assert "shop_image" not in rec


def test_refresh_items_keeps_labels_for_surviving_properties(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    assets.refresh_items(p)

    rec = json.loads(p.read_text())[0]

    assert rec["labels"]["tech_power"] == {"label": "Spirit Power", "signed": True}
    assert rec["labels"]["bonus_sprint_speed"] == {"label": "Sprint Speed", "postfix": "m/s"}
    assert "ability_cooldown" not in rec["labels"]
    assert "ability_charges" not in rec["labels"]


def test_refresh_items_flattens_tooltip_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    assets.refresh_items(p)

    rec = json.loads(p.read_text())[0]

    assert rec["sections"] == [
        {"section": "innate", "text": None, "properties": ["tech_power", "bonus_health"]},
        {
            "section": "passive",
            "text": "Deal bonus damage",
            "properties": ["max_health_loss_percent", "bonus_sprint_speed"],
        },
    ]


def test_loaded_item_defaults_without_display_fields(tmp_path):
    p = tmp_path / "items.json"
    p.write_text(json.dumps([{"id": 3, "name": "Old"}]))

    it = items.item_map(p)[3]

    assert it.labels == {}
    assert it.sections == ()


def test_description_markup_stripped(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    assets.refresh_items(p)

    rec = json.loads(p.read_text())[0]

    assert rec["description"] == "Deal bonus Spirit damage"


def test_clean_text_handles_missing():
    assert assets._clean_text(None) is None
    assert assets._clean_text("") is None
    assert assets._clean_text("<b></b>") is None
    assert assets._clean_text("plain") == "plain"


def test_refresh_items_clears_lookup_caches(tmp_path, monkeypatch):
    p = tmp_path / "items.json"
    p.write_text(json.dumps([{"id": 9, "name": "Old Name"}]))

    assert items.item_name(9, p) == "Old Name"

    monkeypatch.setattr(
        assets.api, "get_json", lambda path, **kw: [dict(ITEM_REC, id=9, name="New Name")]
    )
    assets.refresh_items(p)

    assert items.item_name(9, p) == "New Name"


def test_refresh_heroes_clears_lookup_cache(tmp_path, monkeypatch):
    p = tmp_path / "heroes.json"
    p.write_text(json.dumps([{"id": 5, "name": "Old", "class_name": "hero_old"}]))

    assert heroes.hero_name(5, p) == "Old"

    monkeypatch.setattr(
        assets.api, "get_json", lambda path, **kw: [dict(HERO_REC, id=5, name="New")]
    )
    assets.refresh_heroes(p)

    assert heroes.hero_name(5, p) == "New"


def test_loaded_item_carries_description_and_components(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [ITEM_REC])
    p = tmp_path / "items.json"

    assets.refresh_items(p)

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

    monkeypatch.setattr(assets.api, "get_json", fake)
    p = tmp_path / "abilities.json"

    assert assets.refresh_abilities(p) == 2

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
        assets.api,
        "get_json",
        lambda path, **kw: [{"id": 1, "name": "New", "class_name": "x", "hero": 52}],
    )
    assets.refresh_abilities(p)

    assert abilities.ability_map(p)["x"].name == "New"


def test_archive_snapshots_writes_dated_copies(tmp_path):
    dest = assets.archive_snapshots(tmp_path, dt.date(2026, 7, 6))

    assert dest == tmp_path / "2026-07-06"

    for name in ("heroes.json", "items.json", "abilities.json"):
        assert (dest / name).is_file()

    bundled = json.loads(items.ITEMS_JSON.read_text(encoding="utf-8"))

    assert json.loads((dest / "items.json").read_text()) == bundled


def _make_history(root, dates):
    for d in dates:
        folder = root / d
        folder.mkdir(parents=True)
        (folder / "items.json").write_text(json.dumps([{"id": 1, "name": d}]))


def test_snapshot_asof_picks_latest_on_or_before(tmp_path):
    _make_history(tmp_path, ["2026-06-01", "2026-07-05"])

    assert items.snapshot_asof(dt.date(2026, 7, 6), tmp_path)[1] == "2026-07-05"
    assert items.snapshot_asof(dt.date(2026, 7, 5), tmp_path)[1] == "2026-07-05"
    assert items.snapshot_asof(dt.datetime(2026, 6, 20, 5, tzinfo=dt.UTC), tmp_path)[1] == (
        "2026-06-01"
    )


def test_snapshot_asof_older_than_history_gets_earliest(tmp_path):
    _make_history(tmp_path, ["2026-06-01", "2026-07-05"])

    path, date = items.snapshot_asof(dt.date(2020, 1, 1), tmp_path)

    assert date == "2026-06-01"
    assert items.item_map(path)[1].name == "2026-06-01"


def test_snapshot_asof_without_history_falls_back_to_bundled(tmp_path):
    path, date = items.snapshot_asof(dt.date(2026, 7, 6), tmp_path / "missing")

    assert path == items.ITEMS_JSON
    assert date is None


def test_snapshot_asof_ignores_incomplete_folders(tmp_path):
    (tmp_path / "2026-07-01").mkdir()
    (tmp_path / "notes").mkdir()
    _make_history(tmp_path, ["2026-06-01"])

    assert items.snapshot_asof(dt.date(2026, 7, 6), tmp_path)[1] == "2026-06-01"


def test_loaded_hero_carries_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [HERO_REC])
    p = tmp_path / "heroes.json"

    assets.refresh_heroes(p)

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
    assert assets._measure("20m") == 20
    assert assets._measure("0.2s") == 0.2
    assert assets._measure("-35m") == -35
    assert assets._measure(".3m") == 0.3
    assert assets._measure("1.28") == 1.28
    assert assets._measure(36.0) == 36
    assert assets._measure("whirlwind") == "whirlwind"


def test_refresh_abilities_keeps_tuning_numbers(tmp_path, monkeypatch):
    monkeypatch.setattr(
        assets.api, "get_json", lambda path, **kw: [ABILITY_REC] if "ability" in path else []
    )
    p = tmp_path / "abilities.json"

    assets.refresh_abilities(p)

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
        assets.api, "get_json", lambda path, **kw: [weapon] if "weapon" in path else []
    )
    p = tmp_path / "abilities.json"

    assets.refresh_abilities(p)

    rec = json.loads(p.read_text())[0]

    assert rec["weapon"] == {"bullet_damage": 14.8}
    assert "properties" not in rec
    assert "upgrades" not in rec
