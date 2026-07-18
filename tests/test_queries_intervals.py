import polars as pl
import pytest
from builders import _write_item_history, build_interval_match, build_match

from deadlock_matches import export, queries


def test_compare_intervals_column_gains(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    gains = queries.compare_intervals(games, "souls", 300, movement_pq).collect().sort("interval")

    assert gains.get_column("interval").to_list() == [0, 1, 2, 3, 4, 5]
    assert gains.get_column("gain").to_list() == [1800, 4200, 0, 0, 0, 0]


def test_compare_intervals_source_composite(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    gains = queries.compare_intervals(games, "farm", 300, movement_pq).collect().sort("interval")

    assert gains.get_column("gain").to_list() == [0, 700, 0, 0, 0, 0]


def test_compare_intervals_counts_kills_and_deaths_from_the_deaths_table(movement_pq):
    victim = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    killer = pl.LazyFrame({"match_id": [100], "account_id": [43]})

    deaths = queries.compare_intervals(victim, "deaths", 300, movement_pq).collect()
    kills = queries.compare_intervals(killer, "kills", 300, movement_pq).collect()

    assert deaths.sort("interval")["gain"].to_list() == [1, 0, 0, 0, 0, 0]
    assert kills.sort("interval")["gain"].to_list() == [1, 0, 0, 0, 0, 0]


def test_compare_intervals_unknown_stat(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})

    with pytest.raises(ValueError, match="Unknown compare stat"):
        queries.compare_intervals(games, "ability_points", 300, movement_pq)


def test_compare_stats_sum_the_rift_urn_source(tmp_path):
    info = build_match(match_id=300)
    g = info.players[0].stats[-1].gold_sources.add()
    g.source = 5
    g.gold = 450

    out = tmp_path / "pq"
    out.mkdir()

    for name, df in export.build_tables([info]).items():
        df.write_parquet(out / f"{name}.parquet")

    games = pl.LazyFrame({"match_id": [300], "account_id": [42]})
    rift_urn = queries.compare_intervals(games, "rift_urn", 300, out).collect()

    assert rift_urn.get_column("gain").sum() == 450

    with pytest.raises(ValueError, match="Unknown compare stat"):
        queries.compare_intervals(games, "treasure", 300, out)


def test_cumulative_stat_target_times_interpolates_between_snapshots(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    times = queries.cumulative_stat_target_times(games, [3000], "souls", movement_pq).collect()

    assert times.get_column("target_time_s").to_list() == [300.0]


def test_cumulative_stat_target_times_below_first_snapshot_uses_game_start(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    times = queries.cumulative_stat_target_times(games, [900], "souls", movement_pq).collect()

    assert times.get_column("target_time_s").to_list() == [90.0]


def test_cumulative_stat_target_times_lands_on_a_snapshot_exactly(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    times = queries.cumulative_stat_target_times(games, [6000], "souls", movement_pq).collect()

    assert times.get_column("target_time_s").to_list() == [600.0]


def test_cumulative_stat_target_times_skips_targets_no_game_reaches(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    times = queries.cumulative_stat_target_times(
        games, [3000, 7000], "souls", movement_pq
    ).collect()

    assert times.get_column("target").to_list() == [3000]


def test_cumulative_stat_target_times_unknown_stat(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})

    with pytest.raises(ValueError, match="Unknown cumulative target stat"):
        queries.cumulative_stat_target_times(games, [1600], "ability_points", movement_pq)


def test_cumulative_at_reads_last_sample_before_the_mark(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    souls = queries.cumulative_at(games, "souls", [360, 900], movement_pq).collect()
    farm = queries.cumulative_at(games, "farm", [360, 900], movement_pq).collect()

    assert dict(souls.select("mark_s", "value").iter_rows()) == {360: 1800, 900: 6000}
    assert dict(farm.select("mark_s", "value").iter_rows()) == {360: 0, 900: 700}


def test_cumulative_at_skips_marks_past_match_end(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    souls = queries.cumulative_at(games, "souls", [900, 7200], movement_pq).collect()

    assert souls.get_column("mark_s").to_list() == [900]


def test_game_rates_whole_match(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    souls = queries.game_rates(games, "souls", movement_pq).collect()
    farm = queries.game_rates(games, "farm", movement_pq).collect()

    killer = pl.LazyFrame({"match_id": [100], "account_id": [43]})
    kills = queries.game_rates(killer, "kills", movement_pq).collect()

    assert souls.get_column("rate").to_list() == [6000 * 60 / 1800]
    assert farm.get_column("rate").to_list() == [700 * 60 / 1800]
    assert kills.get_column("rate").to_list() == [1 * 60 / 1800]


def test_game_totals_whole_match(movement_pq):
    games = pl.LazyFrame({"match_id": [100], "account_id": [42]})
    souls = queries.game_totals(games, "souls", movement_pq).collect()

    killer = pl.LazyFrame({"match_id": [100], "account_id": [43]})
    kills = queries.game_totals(killer, "kills", movement_pq).collect()

    assert souls.get_column("total").to_list() == [6000]
    assert souls.get_column("duration_s").to_list() == [1800]
    assert kills.get_column("total").to_list() == [1]


def test_match_intervals_gains_per_interval(interval_pq):
    df = queries.match_intervals(500, 42, parquet_dir=interval_pq)

    assert df.get_column("start_s").to_list() == [0, 300, 600, 900]
    assert df.get_column("souls").to_list() == [3000, 2000, 0, 3000]
    assert df.get_column("damage").to_list() == [1000, 500, 0, 2500]
    assert df.get_column("damage_taken").to_list() == [500, 400, 0, 1100]
    assert df.get_column("creeps").to_list() == [20, 10, 0, 25]
    assert df.get_column("neutrals").to_list() == [2, 3, 0, 4]
    assert df.get_column("denies").to_list() == [4, 0, 0, 2]
    assert df.get_column("assists").to_list() == [2, 1, 0, 4]
    assert df.get_column("obj_damage").to_list() == [300, 0, 0, 1200]
    assert df.get_column("healing").to_list() == [200, 300, 0, 400]
    assert df.get_column("heal_prevented").to_list() == [0, 150, 0, 250]


def test_match_intervals_kills_and_deaths_from_death_record(interval_pq):
    df = queries.match_intervals(500, 42, parquet_dir=interval_pq)

    assert df.get_column("kills").to_list() == [1, 0, 0, 2]
    assert df.get_column("deaths").to_list() == [1, 0, 0, 1]


def test_match_intervals_last_interval_ends_at_match_end(interval_pq):
    df = queries.match_intervals(500, 42, parquet_dir=interval_pq)

    assert df.get_column("end_s").to_list() == [300, 600, 900, 1190]
    assert df.get_column("souls_min")[0] == pytest.approx(600.0)
    assert df.get_column("souls_min")[-1] == pytest.approx(3000 * 60 / 290)


def test_match_intervals_interval_size(interval_pq):
    df = queries.match_intervals(500, 42, interval_s=600, parquet_dir=interval_pq)

    assert df.get_column("start_s").to_list() == [0, 600]
    assert df.get_column("end_s").to_list() == [600, 1190]
    assert df.get_column("souls").to_list() == [5000, 3000]


def test_match_intervals_unknown_match(interval_pq):
    with pytest.raises(ValueError, match="not in the tables"):
        queries.match_intervals(999, 42, parquet_dir=interval_pq)


def test_match_intervals_no_snapshots_for_account(interval_pq):
    with pytest.raises(ValueError, match="no snapshots"):
        queries.match_intervals(500, 99, parquet_dir=interval_pq)


def test_damage_intervals_gains_ordered_by_total(interval_pq):
    df = queries.damage_intervals(500, 42, interval_s=600, parquet_dir=interval_pq)

    gun = df.slice(0, 2)
    shot = df.slice(2, 2)

    assert gun.get_column("damage").to_list() == [50, 100]
    assert gun.get_column("start_s").to_list() == [0, 600]
    assert gun.get_column("end_s").to_list() == [600, 1190]
    assert gun.get_column("total").to_list() == [150, 150]
    assert shot.get_column("damage").to_list() == [40, 50]
    assert shot.get_column("total").to_list() == [90, 90]


def test_damage_intervals_details_on_heroes_only(interval_pq):
    df = queries.damage_intervals(500, 42, interval_s=600, parquet_dir=interval_pq)

    assert df.get_column("source_name").n_unique() == 2
    assert df.get_column("damage").sum() == 240
    assert set(df.get_column("delivery")) == {"gun", "gun_proc"}


def test_damage_intervals_other_stats(interval_pq):
    df = queries.damage_intervals(500, 42, interval_s=600, parquet_dir=interval_pq, stat="healing")

    assert df.get_column("damage").to_list() == [0, 30]


def test_damage_intervals_no_rows_for_account(interval_pq):
    with pytest.raises(ValueError, match="no damage to heroes"):
        queries.damage_intervals(500, 99, parquet_dir=interval_pq)


def test_damage_intervals_hides_zero_value_sources(tmp_path):
    info = build_interval_match()
    dm = info.damage_matrix
    dm.source_details.source_name.append("citadel_ability_dash")
    dm.source_details.stat_type.append(0)

    src = dm.damage_dealers[0].damage_sources.add()
    src.source_details_index = len(dm.source_details.source_name) - 1
    t = src.damage_to_players.add()
    t.target_player_slot = 2
    t.damage.extend([0, 0, 0])

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    _write_item_history(tmp_path)

    df = queries.damage_intervals(500, 42, parquet_dir=tmp_path)

    assert df.get_column("source_name").n_unique() == 2
    assert (df.get_column("total") > 0).all()


def test_enemy_damage_intervals_taken(interval_pq):
    df = queries.enemy_damage_intervals(500, 43, interval_s=600, parquet_dir=interval_pq)

    assert df.get_column("enemy").to_list() == ["Mirage", "Mirage"]
    assert df.get_column("enemy_account_id").to_list() == [42, 42]
    assert df.get_column("damage").to_list() == [90, 150]
    assert df.get_column("start_s").to_list() == [0, 600]
    assert df.get_column("end_s").to_list() == [600, 1190]
    assert df.get_column("total").to_list() == [240, 240]


def test_enemy_damage_intervals_dealt(interval_pq):
    df = queries.enemy_damage_intervals(
        500, 42, interval_s=600, parquet_dir=interval_pq, dealt=True
    )

    assert df.get_column("enemy_account_id").to_list() == [43, 43]
    assert df.get_column("damage").to_list() == [90, 150]
    assert df.get_column("total").to_list() == [240, 240]


def test_enemy_damage_intervals_no_rows(interval_pq):
    with pytest.raises(ValueError, match="no damage taken from heroes"):
        queries.enemy_damage_intervals(500, 99, parquet_dir=interval_pq)

    with pytest.raises(ValueError, match="no damage dealt to heroes"):
        queries.enemy_damage_intervals(500, 99, parquet_dir=interval_pq, dealt=True)


def test_source_intervals_matches_damage_intervals(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    many = queries.source_intervals(games, interval_s=600, parquet_dir=interval_pq).collect()
    one = queries.damage_intervals(500, 42, interval_s=600, parquet_dir=interval_pq)

    assert many.select("source_name", "delivery", "start_s", "end_s", "damage", "total").equals(one)


def test_source_intervals_covers_every_game(two_interval_pq):
    games = pl.DataFrame({"match_id": [500, 501], "account_id": [42, 42]})
    df = queries.source_intervals(games, interval_s=600, parquet_dir=two_interval_pq).collect()

    for match_id in (500, 501):
        part = df.filter(pl.col("match_id") == match_id).select(
            "source_name", "delivery", "start_s", "end_s", "damage", "total"
        )
        one = queries.damage_intervals(match_id, 42, interval_s=600, parquet_dir=two_interval_pq)

        assert part.equals(one)


def test_source_intervals_skips_unknown_players(interval_pq):
    games = pl.DataFrame({"match_id": [500, 500], "account_id": [42, 99]})
    df = queries.source_intervals(games, interval_s=600, parquet_dir=interval_pq).collect()

    assert df.get_column("account_id").unique().to_list() == [42]


def test_source_intervals_flags_short_tail(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    df = queries.source_intervals(games, interval_s=600, parquet_dir=interval_pq).collect()

    assert df.filter(pl.col("end_s") == 600)["full"].all()
    assert not df.filter(pl.col("end_s") == 1190)["full"].any()


def test_source_intervals_other_stats(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    df = queries.source_intervals(
        games, interval_s=600, parquet_dir=interval_pq, stat="healing"
    ).collect()

    assert df.get_column("damage").to_list() == [0, 30]


def test_source_totals_matches_the_source_intervals_final(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    totals = queries.source_totals(games, parquet_dir=interval_pq).collect()
    intervals = queries.source_intervals(games, interval_s=600, parquet_dir=interval_pq).collect()

    ends = (
        intervals.group_by("source_name", "delivery")
        .agg(pl.col("total").max().alias("damage"))
        .sort("source_name")
    )

    assert totals.select("source_name", "delivery", "damage").sort("source_name").equals(ends)


def test_source_totals_drops_creep_and_total_rows(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    df = queries.source_totals(games, parquet_dir=interval_pq).collect()

    assert df.get_column("source_name").to_list() == ["citadel_weapon_mirage", "Mystic Shot"]
    assert df.get_column("damage").to_list() == [150, 90]


def test_source_totals_covers_every_game(two_interval_pq):
    games = pl.DataFrame({"match_id": [500, 501], "account_id": [42, 42]})
    df = queries.source_totals(games, parquet_dir=two_interval_pq).collect()

    for match_id in (500, 501):
        part = df.filter(pl.col("match_id") == match_id).get_column("damage").sum()

        assert part == 240


def test_source_totals_skips_unknown_players(interval_pq):
    games = pl.DataFrame({"match_id": [500, 500], "account_id": [42, 99]})
    df = queries.source_totals(games, parquet_dir=interval_pq).collect()

    assert df.get_column("account_id").unique().to_list() == [42]


def test_source_totals_other_stats(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    df = queries.source_totals(games, parquet_dir=interval_pq, stat="healing").collect()

    assert df.get_column("source_name").to_list() == ["Dust Devil"]
    assert df.get_column("damage").to_list() == [30]


def test_enemy_damage_totals_dealt_sums_hero_sources(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    df = queries.enemy_damage_totals(games, parquet_dir=interval_pq, dealt=True).collect()

    assert df.get_column("enemy_account_id").to_list() == [43]
    assert df.get_column("damage").to_list() == [240]
    assert df.get_column("enemy").to_list() == ["Infernus"]


def test_enemy_damage_totals_taken_flips_direction(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [43]})
    df = queries.enemy_damage_totals(games, parquet_dir=interval_pq).collect()

    assert df.get_column("enemy_account_id").to_list() == [42]
    assert df.get_column("damage").to_list() == [240]


def test_enemy_damage_totals_matches_the_intervals_final(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    totals = queries.enemy_damage_totals(games, parquet_dir=interval_pq, dealt=True).collect()
    intervals = queries.enemy_damage_intervals(
        500, 42, interval_s=600, parquet_dir=interval_pq, dealt=True
    )

    ends = intervals.group_by("enemy_account_id").agg(pl.col("total").max().alias("damage"))

    assert totals.select("enemy_account_id", "damage").equals(ends)


def test_enemy_damage_totals_skips_unknown_players(interval_pq):
    games = pl.DataFrame({"match_id": [500, 500], "account_id": [42, 99]})
    df = queries.enemy_damage_totals(games, parquet_dir=interval_pq, dealt=True).collect()

    assert df.get_column("account_id").unique().to_list() == [42]


def test_team_intervals_gains_and_lead(pq):
    df = queries.team_intervals(100, 300, pq)

    assert df.get_column("start_s").to_list() == [0, 300]
    assert df.get_column("end_s").to_list() == [300, 600]
    assert df.get_column("souls_team1").to_list() == [1800, 4200]
    assert df.get_column("souls_team0").to_list() == [0, 0]
    assert df.get_column("lead").to_list() == [-1800, -6000]


def test_team_intervals_unknown_match(pq):
    with pytest.raises(ValueError, match="not in the tables"):
        queries.team_intervals(999, parquet_dir=pq)
