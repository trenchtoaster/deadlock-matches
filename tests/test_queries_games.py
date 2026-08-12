import datetime as dt

import polars as pl
import pytest
from builders import (
    LOCAL_DAY,
    _write_effective_assets,
    _write_item_history,
    add_custom_stats,
    build_heal_match,
    build_match,
    build_movement_match,
    build_upgrade_match,
)

from deadlock_matches import export, queries, schemas


def test_damage_by_source_totals_share_and_rate(pq):
    df = queries.damage_by_source("Mirage", accounts=[42], parquet_dir=pq)

    assert df.columns[0] == "games"
    assert df.get_column("total").to_list() == [150, 90]
    assert df.get_column("games").to_list() == [1, 1]
    assert df.get_column("per_min").to_list() == [5.0, 3.0]
    assert df.get_column("per_min_owned").to_list() == [None, 3.6]
    assert df.get_column("percent").sum() == pytest.approx(100.0)


def test_damage_source_measures_group_damage_and_healing(pq, heal_pq):
    damage = queries.summarize(
        queries.damage_source_games,
        by="delivery",
        measures=["total", "games"],
        hero="Mirage",
        accounts=[42],
        parquet_dir=pq,
    ).collect()
    healing = queries.summarize(
        queries.damage_source_games,
        by="delivery",
        measures=["total", "self"],
        hero="Mirage",
        accounts=[42],
        parquet_dir=heal_pq,
        stat="healing",
    ).collect()

    assert dict(damage.select("delivery", "total").iter_rows()) == {
        "gun": 150,
        "gun_proc": 90,
    }
    assert damage.get_column("games").to_list() == [1, 1]
    assert healing.get_column("total").sum() == 80
    assert healing.get_column("self").sum() == 50


def test_damage_source_games_counts_player_games_not_match_ids():
    rows = pl.LazyFrame(
        {
            "match_id": [100, 100],
            "account_id": [42, 43],
            "amount": [10, 20],
            "game_minutes": [10.0, 10.0],
        }
    )
    df = queries.summarize(
        queries.damage_source_games,
        measures=("games", "minutes"),
        lf=rows,
    ).collect()

    assert df.item(0, "games") == 2
    assert df.item(0, "minutes") == 20.0


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

    with pytest.raises(queries.NoGames, match="No Ranked games of"):
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

    with pytest.raises(queries.NoGames, match="No Ranked games of"):
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


def test_soul_source_measures_group_at_runtime(souls_pq):
    df = queries.summarize(
        queries.soul_source_games,
        by="group",
        measures=["souls", "games"],
        hero="Mirage",
        accounts=[42],
        parquet_dir=souls_pq,
        tz="America/Chicago",
    ).collect()
    totals = dict(df.select("group", "souls").iter_rows())

    assert totals["waves"] == 2500
    assert totals["combat"] == 600
    assert totals["objectives"] == 800


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


def test_souls_by_source_matches_lifts_mode_filter(tmp_path):
    info = build_movement_match(100)
    info.ranked_type = 0

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    with pytest.raises(ValueError):
        queries.souls_by_source("Mirage", accounts=[42], parquet_dir=tmp_path)

    kept = queries.souls_by_source("Mirage", accounts=[42], matches=[100], parquet_dir=tmp_path)

    assert kept.get_column("souls").sum() == 700


def test_damage_source_games_matches_lifts_mode_filter(tmp_path):
    info = build_match(100)
    info.ranked_type = 0

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_item_history(tmp_path)

    df = queries.summarize(
        queries.damage_source_games,
        by="source_name",
        measures=["total", "minutes", "per_window_game"],
        hero="Mirage",
        accounts=[42],
        matches=[100],
        parquet_dir=tmp_path,
    ).collect()

    assert df.get_column("total").sum() == 240
    assert set(df.get_column("minutes").to_list()) == {30.0}
    assert None not in df.get_column("per_window_game").to_list()


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

    with pytest.raises(queries.NoGames, match="No Ranked games of"):
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


def test_combat_hero_records_uses_weighted_rates(tmp_path):
    first = build_match(match_id=100)
    add_custom_stats(
        first,
        [
            ("Enemy Hero Accuracy##Shots", 100),
            ("Enemy Hero Accuracy##Hits", 25),
            ("Enemy Hero Accuracy##Headshots", 5),
            ("Parry Success", 2),
        ],
    )
    second = build_match(match_id=101)
    add_custom_stats(
        second,
        [
            ("Enemy Hero Accuracy##Shots", 300),
            ("Enemy Hero Accuracy##Hits", 150),
            ("Enemy Hero Accuracy##Headshots", 75),
            ("Parry Success", 3),
            ("Parry Miss", 1),
        ],
    )
    haze = build_match(match_id=102)
    haze.players[0].hero_id = 13
    add_custom_stats(
        haze,
        [
            ("Enemy Hero Accuracy##Shots", 200),
            ("Enemy Hero Accuracy##Hits", 100),
            ("Enemy Hero Accuracy##Headshots", 25),
        ],
    )

    for name, df in export.build_tables([first, second, haze], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.combat_hero_records(accounts=[42], parquet_dir=tmp_path, tz="America/Chicago")
    rows = {row["hero"]: row for row in df.iter_rows(named=True)}

    assert rows["Mirage"]["games"] == 2
    assert rows["Mirage"]["shots"] == 400
    assert rows["Mirage"]["hits"] == 175
    assert rows["Mirage"]["headshots"] == 80
    assert rows["Mirage"]["hit_pct"] == 43.8
    assert rows["Mirage"]["headshot_pct"] == 45.7
    assert rows["Mirage"]["parries"] == 5
    assert rows["Mirage"]["missed_parries"] == 1
    assert rows["Haze"]["games"] == 1
    assert rows["Haze"]["hit_pct"] == 50.0
    assert rows["Haze"]["headshot_pct"] == 25.0


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

    with pytest.raises(queries.NoGames, match="No Ranked games of"):
        queries.combat_game_records("Haze", accounts=[42], parquet_dir=pq)


def test_hero_damage_measures_split_the_bullet_series(bullet_pq):
    df = queries.summarize(
        queries.hero_damage_games(matches=[100]),
        by="account_id",
        measures=("total", "gun", "gun_body", "gun_headshot", "targets"),
        parquet_dir=bullet_pq,
    ).collect()
    row = df.row(0, named=True)

    assert row["account_id"] == 42
    assert row["gun_body"] == 150
    assert row["gun_headshot"] == 60
    assert row["gun"] == row["gun_body"] + row["gun_headshot"]
    assert row["total"] == 300
    assert row["targets"] == 1


def test_hero_damage_drops_screen_totals_and_npc_targets(bullet_pq):
    df = queries.summarize(
        queries.hero_damage_games(),
        by="source_class",
        measures=("total",),
        parquet_dir=bullet_pq,
    ).collect()

    assert dict(df.iter_rows()) == {
        "citadel_weapon_mirage": 150,
        "citadel_weapon_mirage_crit": 60,
        "upgrade_crackshot": 90,
    }


def test_hero_damage_filters_one_source_class(bullet_pq):
    total = (
        queries.summarize(
            queries.hero_damage_games(accounts=[42], matches=[100]),
            measures=("total",),
            filters={"source_class": "upgrade_crackshot"},
            parquet_dir=bullet_pq,
        )
        .collect()
        .item()
    )

    assert total == 90


def test_hero_damage_grain_is_unique(bullet_pq):
    rows = queries.view_frame(
        queries.hero_damage_games(matches=[100]), parquet_dir=bullet_pq
    ).collect()

    queries.validate_grain(queries.hero_damage_games, rows)


def test_buff_games_split_permanent_from_bridge(buff_pq):
    df = queries.summarize(
        queries.buff_games(),
        by="account_id",
        measures=("held", "bridge"),
        parquet_dir=buff_pq,
    ).collect()

    assert dict(df.select("account_id", "held").iter_rows()) == {42: 7, 43: 1}
    assert dict(df.select("account_id", "bridge").iter_rows()) == {42: 2, 43: 0}


def test_buff_games_group_by_family_and_join_players(buff_pq):
    df = queries.summarize(
        queries.buff_games(accounts=[42]),
        by=("hero", "buff"),
        measures=("held",),
        parquet_dir=buff_pq,
    ).collect()

    assert df.get_column("hero").unique().to_list() == ["Mirage"]
    assert dict(df.select("buff", "held").iter_rows()) == {"casting": 0, "hp": 4, "wp": 3}


def _silent_mystic_shot(match_id):
    """An upgrade match where Mystic Shot was bought but never landed a proc."""
    info = build_upgrade_match(match_id=match_id)
    del info.damage_matrix.damage_dealers[0].damage_sources[3]

    return info


def _write(infos, path):
    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(path / f"{name}.parquet")


def test_per_1k_divides_by_every_soul_spent_including_a_game_the_item_sat_out(tmp_path):
    _write([build_upgrade_match(310), _silent_mystic_shot(311)], tmp_path)
    _write_effective_assets(tmp_path)

    df = queries.damage_by_source("Mirage", accounts=[42], parquet_dir=tmp_path)
    row = next(r for r in df.iter_rows(named=True) if r["source_name"] == "Mystic Shot")

    assert row["games"] == 1
    assert row["per_1k"] == 36.0


def test_owned_minutes_count_a_game_the_item_dealt_nothing_in(tmp_path):
    _write([build_upgrade_match(310), _silent_mystic_shot(311)], tmp_path)
    _write_item_history(tmp_path)

    one, two = (
        queries.summarize(
            queries.damage_source_games,
            by="source_name",
            measures=("owned_minutes",),
            hero="Mirage",
            accounts=[42],
            matches=matches,
            parquet_dir=tmp_path,
        )
        .collect()
        .filter(pl.col("source_name") == "Mystic Shot")
        .item(0, "owned_minutes")
        for matches in ([310], [310, 311])
    )

    assert two == pytest.approx(one * 2)


def test_silent_item_rows_use_the_delivery_from_their_own_era(tmp_path):
    first = build_upgrade_match(310)
    second = _silent_mystic_shot(311)
    second.start_time += 86400
    _write([first, second], tmp_path)

    eras = [
        {
            "item_id": 9000,
            "name": "Mystic Shot",
            "class_name": "upgrade_crackshot",
            "cost": 500,
            "slot": slot,
            "tier": 1,
            "is_active": False,
            "description": None,
            "era_from": era_from,
            "client_version": version,
        }
        for slot, era_from, version in (
            ("weapon", dt.datetime(2020, 1, 1, tzinfo=dt.UTC), 1),
            (
                "spirit",
                dt.datetime.fromtimestamp(second.start_time - 1, tz=dt.UTC),
                2,
            ),
        )
    ]
    path = schemas.table_path("item_history", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    schemas.conform("item_history", eras).write_parquet(path)

    df = queries.summarize(
        queries.damage_source_games,
        by=("match_id", "delivery"),
        measures=("owned_minutes",),
        hero="Mirage",
        accounts=[42],
        matches=[310, 311],
        parquet_dir=tmp_path,
    ).collect()
    mystic = df.filter(pl.col("owned_minutes") > 0)

    assert dict(mystic.select("match_id", "delivery").iter_rows()) == {
        310: "gun_proc",
        311: "spirit_proc",
    }


def test_window_measures_divide_by_every_game_of_the_hero(tmp_path):
    _write([build_heal_match(100), build_match(101)], tmp_path)
    _write_item_history(tmp_path)

    df = queries.summarize(
        queries.damage_source_games,
        measures=("total", "games", "per_game", "per_window_game", "per_window_min", "share"),
        hero="Mirage",
        accounts=[42],
        matches=[100, 101],
        stat="heal_prevented",
        parquet_dir=tmp_path,
    ).collect()
    row = df.row(0, named=True)

    assert row["total"] == 25
    assert row["games"] == 1
    assert row["per_game"] == 25.0
    assert row["per_window_game"] == 12.5
    assert row["per_window_min"] == pytest.approx(25 / 60)
    assert row["share"] == 1.0


def test_a_share_of_the_window_adds_to_one_across_the_sources(pq):
    df = queries.summarize(
        queries.damage_source_games,
        by="source_name",
        measures=("share",),
        hero="Mirage",
        accounts=[42],
        parquet_dir=pq,
    ).collect()

    assert df.get_column("share").sum() == pytest.approx(1.0)


def test_combat_games_counts_every_game_and_rates_read_the_summed_counters(tmp_path):
    first = build_match(100)
    add_custom_stats(
        first,
        [
            ("Enemy Hero Accuracy##Shots", 100),
            ("Enemy Hero Accuracy##Hits", 40),
            ("Enemy Hero Accuracy##Headshots", 10),
            ("Parry Success", 3),
            ("Parry Miss", 5),
            ("Enemy Hero Accuracy - Incoming##Shots", 50),
            ("Enemy Hero Accuracy - Incoming##Hits", 20),
        ],
    )
    _write([first, build_match(101)], tmp_path)
    _write_item_history(tmp_path)

    df = queries.summarize(
        queries.combat_games,
        measures=(
            "games",
            "shots",
            "hits",
            "hit_rate",
            "headshot_rate",
            "incoming_hit_rate",
            "parries_per_game",
            "missed_parries_per_game",
        ),
        hero="Mirage",
        accounts=[42],
        parquet_dir=tmp_path,
    ).collect()
    row = df.row(0, named=True)

    assert row["games"] == 2
    assert row["shots"] == 100
    assert row["hit_rate"] == pytest.approx(0.4)
    assert row["headshot_rate"] == pytest.approx(0.25)
    assert row["incoming_hit_rate"] == pytest.approx(0.4)
    assert row["parries_per_game"] == pytest.approx(1.5)
    assert row["missed_parries_per_game"] == pytest.approx(2.5)
