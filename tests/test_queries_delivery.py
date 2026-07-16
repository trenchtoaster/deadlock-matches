import datetime as dt

import polars as pl
from builders import LOCAL_DAY, _write_item_history

from deadlock_matches import queries, schemas


def test_damage_categories():
    frame = pl.LazyFrame(
        {
            "source_class": [
                "Bullet",
                "Ability",
                "Melee",
                "UnknownAbility",
                "citadel_weapon_mirage_set",
                "upgrade_escalating_exposure",
                "mirage_tornado",
                "ability_blood_bomb_bloodspill",
            ]
        }
    )
    got = frame.select(queries.damage_category()).collect().to_series().to_list()

    assert got == ["total", "total", "total", "total", "gun", "item", "ability", "ability"]


def test_damage_delivery(tmp_path):
    slots = {
        "upgrade_crackshot": "weapon",
        "upgrade_headhunter": "weapon",
        "upgrade_toxic_bullets": "weapon",
        "upgrade_ethereal_bullets": "spirit",
        "upgrade_quick_silver": "spirit",
        "upgrade_siphon_bullets": "vitality",
        "upgrade_escalating_exposure": "spirit",
    }
    _write_item_history(tmp_path, slots)
    expected = {
        "Bullet": None,
        "Ability": None,
        "citadel_weapon_mirage_set": "gun",
        "citadel_weapon_mirage_set_crit": "gun",
        "upgrade_crackshot": "gun_proc",
        "upgrade_headhunter": "gun_proc",
        "upgrade_toxic_bullets": "gun_proc",
        "upgrade_ethereal_bullets": "spirit_proc",
        "upgrade_quick_silver": "spirit_proc",
        "upgrade_siphon_bullets": "gun_proc",
        "upgrade_escalating_exposure": "spirit_proc",
        "mirage_tornado": "ability",
        "upgrade_nonexistent_item": "spirit_proc",
    }
    classes = list(expected)
    pl.DataFrame(
        {
            "match_id": [1],
            "start_time": [dt.datetime(2026, 2, 1, tzinfo=dt.UTC)],
        }
    ).write_parquet(tmp_path / "matches.parquet")
    frame = pl.LazyFrame({"match_id": [1] * len(classes), "source_class": classes})

    out = queries.with_delivery(frame, tmp_path).collect()
    got = dict(out.select("source_class", "delivery").iter_rows())

    assert got == expected


def test_delivery_follows_item_era(tmp_path):
    rows = [
        {
            "item_id": 9000,
            "name": "Flux",
            "class_name": "upgrade_flux",
            "cost": 500,
            "slot": slot,
            "tier": 1,
            "is_active": False,
            "description": None,
            "era_from": era,
            "client_version": version,
        }
        for slot, era, version in (
            ("weapon", dt.datetime(2026, 1, 1, tzinfo=dt.UTC), 100),
            ("spirit", dt.datetime(2026, 3, 1, tzinfo=dt.UTC), 200),
        )
    ]
    path = schemas.table_path("item_history", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    schemas.conform("item_history", rows).write_parquet(path)
    pl.DataFrame(
        {
            "match_id": [1, 2],
            "start_time": [
                dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
                dt.datetime(2026, 4, 1, tzinfo=dt.UTC),
            ],
        }
    ).write_parquet(tmp_path / "matches.parquet")
    frame = pl.LazyFrame({"match_id": [1, 2], "source_class": ["upgrade_flux", "upgrade_flux"]})

    out = queries.with_delivery(frame, tmp_path).collect().sort("match_id")

    assert out.get_column("delivery").to_list() == ["gun_proc", "spirit_proc"]


def test_hero_damage_delivery_column(pq):
    df = queries.hero_damage(parquet_dir=pq, tz="America/Chicago").collect()
    got = dict(df.select("source_class", "delivery").iter_rows())

    assert got == {"citadel_weapon_mirage": "gun", "upgrade_crackshot": "gun_proc"}


def test_hero_damage_keeps_only_detail_rows_on_heroes(pq):
    df = queries.hero_damage(parquet_dir=pq, tz="America/Chicago").collect()
    df = df.sort("damage", descending=True)

    assert df.get_column("source_class").to_list() == ["citadel_weapon_mirage", "upgrade_crackshot"]
    assert df.get_column("target_account_id").to_list() == [43, 43]
    assert df.get_column("damage").to_list() == [150, 90]


def test_hero_damage_stat_filter(pq):
    df = queries.hero_damage("healing", parquet_dir=pq, tz="America/Chicago").collect()

    assert df.get_column("source_class").to_list() == ["mirage_tornado"]
    assert df.get_column("damage").to_list() == [30]


def test_hero_damage_adds_dealer_hero_and_day(pq):
    df = queries.hero_damage(parquet_dir=pq, tz="America/Chicago").collect()

    assert df.get_column("hero").to_list() == ["Mirage", "Mirage"]
    assert df.get_column("day").to_list() == [LOCAL_DAY, LOCAL_DAY]
