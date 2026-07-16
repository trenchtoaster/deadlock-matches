import datetime as dt

import polars as pl
import pytest
from builders import (
    LOCAL_DAY,
    _write_item_history,
    add_custom_stats,
    build_heal_match,
    build_match,
    build_movement_match,
)

from deadlock_matches import export, queries


def test_damage_by_source_totals_share_and_rate(pq):
    df = queries.damage_by_source("Mirage", accounts=[42], parquet_dir=pq)

    assert df.columns[0] == "games"
    assert df.get_column("total").to_list() == [150, 90]
    assert df.get_column("games").to_list() == [1, 1]
    assert df.get_column("per_min").to_list() == [5.0, 3.0]
    assert df.get_column("per_min_owned").to_list() == [None, 3.6]
    assert df.get_column("percent").sum() == pytest.approx(100.0)


def test_damage_by_source_item_rate_ends_at_the_sell(sold_pq):
    df = queries.damage_by_source("Mirage", accounts=[42], parquet_dir=sold_pq)
    row = df.filter(pl.col("source_name") == "Mystic Shot")

    assert row.get_column("per_min").to_list() == [3.0]
    assert row.get_column("per_min_owned").to_list() == [9.0]


def test_damage_by_source_item_rate_sums_rebuy_windows(rebuy_pq):
    df = queries.damage_by_source("Mirage", accounts=[42], parquet_dir=rebuy_pq)
    row = df.filter(pl.col("source_name") == "Mystic Shot")

    assert row.get_column("per_min").to_list() == [3.0]
    assert row.get_column("per_min_owned").to_list() == [4.5]


def test_damage_by_source_matches_filter(pq):
    kept = queries.damage_by_source("Mirage", accounts=[42], matches=[100], parquet_dir=pq)

    assert kept.get_column("total").to_list() == [150, 90]

    with pytest.raises(ValueError):
        queries.damage_by_source("Mirage", accounts=[42], matches=[999], parquet_dir=pq)


def test_damage_by_source_raises_without_games(pq):
    with pytest.raises(ValueError):
        queries.damage_by_source("Haze", accounts=[42], parquet_dir=pq)

    with pytest.raises(ValueError):
        queries.damage_by_source("Mirage", accounts=[], parquet_dir=pq)


def test_damage_by_source_per_1k_souls(effective_pq):
    df = queries.damage_by_source("Mirage", accounts=[42], parquet_dir=effective_pq)
    by_source = {r["source_name"]: r["per_1k"] for r in df.iter_rows(named=True)}

    assert by_source["Mystic Shot"] == 72.0
    assert by_source["citadel_weapon_mirage"] is None


def test_damage_by_source_per_1k_null_without_history(no_history_pq):
    df = queries.damage_by_source("Mirage", accounts=[42], parquet_dir=no_history_pq)

    assert df.get_column("per_1k").to_list() == [None, None]


def test_damage_by_source_healing_stat(heal_pq):
    df = queries.damage_by_source("Mirage", accounts=[42], parquet_dir=heal_pq, stat="healing")

    assert df.get_column("source_name").to_list() == ["Toxic Bullets", "Dust Devil"]
    assert df.get_column("total").to_list() == [50, 30]
    assert df.get_column("per_min").to_list() == [1.7, 1.0]
    assert df.get_column("per_min_owned").to_list() == [None, None]
    assert df.get_column("percent").to_list() == [62.5, 37.5]


def test_damage_by_source_healing_stat_raises_without_rows(pq):
    with pytest.raises(ValueError, match="no mitigated rows"):
        queries.damage_by_source("Mirage", accounts=[42], parquet_dir=pq, stat="mitigated")


def test_damage_by_source_heal_prevented_stat(heal_pq):
    df = queries.damage_by_source(
        "Mirage", accounts=[42], parquet_dir=heal_pq, stat="heal_prevented"
    )

    assert df.get_column("source_name").to_list() == ["Toxic Bullets"]
    assert df.get_column("delivery").to_list() == ["gun_proc"]
    assert df.get_column("total").to_list() == [25]
    assert df.get_column("per_min").to_list() == [0.8]
    assert df.get_column("percent").to_list() == [100.0]


def test_damage_by_source_per_min_skips_stat_free_games(tmp_path):
    infos = [build_heal_match(100), build_match(101)]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_item_history(tmp_path)

    df = queries.damage_by_source(
        "Mirage", accounts=[42], matches=[100, 101], parquet_dir=tmp_path, stat="heal_prevented"
    )

    assert df.get_column("total").to_list() == [25]
    assert df.get_column("games").to_list() == [1]
    assert df.get_column("per_min").to_list() == [0.8]


def test_damage_by_source_drops_zero_value_sources(heal_pq):
    df = queries.damage_by_source("Mirage", accounts=[42], parquet_dir=heal_pq)

    assert len(df) == 2
    assert df.get_column("total").to_list() == [150, 90]


def test_damage_game_records_splits_deliveries(pq):
    df = queries.damage_game_records("Mirage", accounts=[42], parquet_dir=pq, tz="America/Chicago")
    row = df.row(0, named=True)

    assert len(df) == 1
    assert row["total"] == 240
    assert row["gun"] == 150
    assert row["abilities"] == 0
    assert row["items"] == 90
    assert row["gun_pct"] == 62.5
    assert row["abilities_pct"] == 0.0
    assert row["items_pct"] == 37.5
    assert row["won"] is True
    assert row["day"] == LOCAL_DAY


def test_damage_game_records_resolves_fuzzy_hero_names(pq):
    df = queries.damage_game_records("mirage", accounts=[42], parquet_dir=pq, tz="America/Chicago")

    assert df.get_column("hero").to_list() == ["Mirage"]


def test_damage_game_records_day_filters(record_pq):
    def records(**kwargs):
        return queries.damage_game_records(
            "Mirage", accounts=[42], parquet_dir=record_pq, tz="America/Chicago", **kwargs
        )

    all_games = records()
    last = records(days=1)
    since = records(since=str(LOCAL_DAY + dt.timedelta(days=1)))

    assert len(all_games) == 5
    assert all_games.get_column("match_id").to_list()[-2:] == [4, 5]
    assert last.get_column("match_id").to_list() == [4, 5]
    assert since.get_column("match_id").to_list() == [4, 5]


def test_damage_game_records_raises(pq):
    with pytest.raises(ValueError, match="Unknown hero"):
        queries.damage_game_records("Nobody", accounts=[42], parquet_dir=pq)

    with pytest.raises(ValueError, match="no games"):
        queries.damage_game_records("Haze", accounts=[42], parquet_dir=pq)


def test_healing_game_records_splits_delivery_and_recipient(heal_pq):
    df = queries.healing_game_records(
        "Mirage", accounts=[42], parquet_dir=heal_pq, tz="America/Chicago"
    )
    row = df.row(0, named=True)

    assert len(df) == 1
    assert row["total"] == 80
    assert row["abilities"] == 30
    assert row["items"] == 50
    assert row["self"] == 50
    assert row["prevented"] == 25
    assert row["abilities_pct"] == 37.5
    assert row["items_pct"] == 62.5
    assert row["self_pct"] == 62.5
    assert row["won"] is True
    assert row["day"] == LOCAL_DAY


def test_healing_game_records_prevented_zero_without_rows(pq):
    df = queries.healing_game_records("Mirage", accounts=[42], parquet_dir=pq, tz="America/Chicago")

    assert df.get_column("prevented").to_list() == [0]


def test_healing_game_records_day_filters(record_pq):
    def records(**kwargs):
        return queries.healing_game_records(
            "Mirage", accounts=[42], parquet_dir=record_pq, tz="America/Chicago", **kwargs
        )

    all_games = records()
    last = records(days=1)
    since = records(since=str(LOCAL_DAY + dt.timedelta(days=1)))

    assert len(all_games) == 5
    assert last.get_column("match_id").to_list() == [4, 5]
    assert since.get_column("match_id").to_list() == [4, 5]


def test_healing_game_records_raises(pq):
    with pytest.raises(ValueError, match="Unknown hero"):
        queries.healing_game_records("Nobody", accounts=[42], parquet_dir=pq)

    with pytest.raises(ValueError, match="no games"):
        queries.healing_game_records("Haze", accounts=[42], parquet_dir=pq)


def test_souls_by_source_drops_sources_that_never_paid(souls_pq):
    df = queries.souls_by_source("Mirage", accounts=[42], parquet_dir=souls_pq)

    assert "denies" not in df.get_column("source_name").to_list()
    assert set(df.get_column("games").to_list()) == {1}


def test_souls_by_source_sums_orbs(movement_pq):
    df = queries.souls_by_source("Mirage", accounts=[42], parquet_dir=movement_pq)

    assert df.columns[0] == "games"
    assert df.get_column("souls").sum() == 700
    assert df.get_column("games").to_list() == [1]
    assert df.get_column("percent").to_list() == [100.0]


def test_souls_by_source_minutes_cover_only_the_paying_games(tmp_path):
    infos = [build_movement_match(100), build_match(101)]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.souls_by_source("Mirage", accounts=[42], parquet_dir=tmp_path)

    assert df.get_column("games").to_list() == [1]
    assert df.get_column("minutes").to_list() == [30.0]


def test_souls_by_source_matches_filter(movement_pq):
    kept = queries.souls_by_source("Mirage", accounts=[42], matches=[100], parquet_dir=movement_pq)

    assert kept.get_column("souls").sum() == 700

    with pytest.raises(ValueError):
        queries.souls_by_source("Mirage", accounts=[42], matches=[999], parquet_dir=movement_pq)


def test_souls_by_source_raises_without_souls(pq):
    with pytest.raises(ValueError):
        queries.souls_by_source("Mirage", accounts=[42], parquet_dir=pq)


def test_souls_game_records_splits_groups(souls_pq):
    df = queries.souls_game_records(
        "Mirage", accounts=[42], parquet_dir=souls_pq, tz="America/Chicago"
    )
    row = df.row(0, named=True)

    assert len(df) == 1
    assert row["total"] == 4000
    assert row["waves"] == 2500
    assert row["roaming"] == 0
    assert row["combat"] == 600
    assert row["objectives"] == 800
    assert row["waves_pct"] == 62.5
    assert row["roaming_pct"] == 0.0
    assert row["combat_pct"] == 15.0
    assert row["objectives_pct"] == 20.0
    assert row["won"] is True
    assert row["day"] == LOCAL_DAY


def test_souls_game_records_day_filters(record_pq):
    def records(**kwargs):
        return queries.souls_game_records(
            "Mirage", accounts=[42], parquet_dir=record_pq, tz="America/Chicago", **kwargs
        )

    all_games = records()
    last = records(days=1)
    since = records(since=str(LOCAL_DAY + dt.timedelta(days=1)))

    assert len(all_games) == 5
    assert last.get_column("match_id").to_list() == [4, 5]
    assert since.get_column("match_id").to_list() == [4, 5]


def test_souls_game_records_raises(pq):
    with pytest.raises(ValueError, match="Unknown hero"):
        queries.souls_game_records("Nobody", accounts=[42], parquet_dir=pq)

    with pytest.raises(ValueError, match="no games"):
        queries.souls_game_records("Haze", accounts=[42], parquet_dir=pq)


def test_combat_game_records_counts_and_rates(tmp_path):
    info = build_match()
    add_custom_stats(
        info,
        [
            ("Enemy Hero Accuracy##Shots", 1000),
            ("Enemy Hero Accuracy##Hits", 250),
            ("Enemy Hero Accuracy##Headshots", 50),
            ("Enemy Hero Accuracy - Incoming##Shots", 800),
            ("Parry Success", 3),
            ("Parry Miss", 2),
        ],
    )

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.combat_game_records(
        "Mirage", accounts=[42], parquet_dir=tmp_path, tz="America/Chicago"
    )
    row = df.row(0, named=True)

    assert len(df) == 1
    assert row["shots"] == 1000
    assert row["hits"] == 250
    assert row["headshots"] == 50
    assert row["parries"] == 3
    assert row["missed_parries"] == 2
    assert row["hit_pct"] == 25.0
    assert row["headshot_pct"] == 20.0
    assert row["won"] is True
    assert row["day"] == LOCAL_DAY


def test_combat_game_records_fills_missing_counters(pq):
    df = queries.combat_game_records("Mirage", accounts=[42], parquet_dir=pq)
    row = df.row(0, named=True)

    assert row["shots"] == 0
    assert row["parries"] == 0
    assert row["hit_pct"] is None
    assert row["headshot_pct"] is None


def test_combat_game_records_day_filters(record_pq):
    def records(**kwargs):
        return queries.combat_game_records(
            "Mirage", accounts=[42], parquet_dir=record_pq, tz="America/Chicago", **kwargs
        )

    all_games = records()
    last = records(days=1)
    since = records(since=str(LOCAL_DAY + dt.timedelta(days=1)))

    assert len(all_games) == 5
    assert last.get_column("match_id").to_list() == [4, 5]
    assert since.get_column("match_id").to_list() == [4, 5]


def test_combat_game_records_raises(pq):
    with pytest.raises(ValueError, match="Unknown hero"):
        queries.combat_game_records("Nobody", accounts=[42], parquet_dir=pq)

    with pytest.raises(ValueError, match="no games"):
        queries.combat_game_records("Haze", accounts=[42], parquet_dir=pq)
