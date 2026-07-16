import polars as pl
import pytest
from builders import LOCAL_DAY, build_match, build_movement_match

from deadlock_matches import export, queries


def test_movement_profile_metrics(movement_pq):
    df = queries.movement_profile(movement_pq).collect()
    me = df.filter(pl.col("account_id") == 42)

    assert me.get_column("alive_s")[0] == 10
    assert me.get_column("slide_percent")[0] == pytest.approx(20.0)
    assert me.get_column("in_air_percent")[0] == pytest.approx(20.0)
    assert me.get_column("zipline_percent")[0] == pytest.approx(10.0)
    assert me.get_column("combat_percent")[0] == pytest.approx(40.0)
    assert me.get_column("dashes_min")[0] == pytest.approx(6.0)
    assert me.get_column("air_dashes_min")[0] == pytest.approx(6.0)
    assert me.get_column("distance")[0] == pytest.approx(700.0)
    assert me.get_column("stationary_percent")[0] == pytest.approx(0.0)


def test_movement_profile_stationary_player(movement_pq):
    df = queries.movement_profile(movement_pq).collect()
    camper = df.filter(pl.col("account_id") == 43)

    assert camper.get_column("distance")[0] == pytest.approx(0.0)
    assert camper.get_column("stationary_percent")[0] == pytest.approx(100.0)


def test_movement_profile_single_sample_track(tmp_path):
    info = build_movement_match()
    p = info.match_paths.paths.add()
    p.player_slot = 99
    p.x_max = 10000.0
    p.y_max = 10000.0
    p.x_pos.append(1)
    p.y_pos.append(1)
    p.health.append(100)

    ghost = info.players.add()
    ghost.account_id = 99
    ghost.player_slot = 99

    for name, df in export.build_tables([info]).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.movement_profile(tmp_path).collect()
    lone = df.filter(pl.col("account_id") == 99)

    assert lone.get_column("moving_s")[0] == 0
    assert lone.get_column("distance_min")[0] is None
    assert lone.get_column("souls_per_1000_units")[0] is None


def test_movement_profile_without_raw_movement(tmp_path):
    infos = [build_movement_match()]
    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.movement_profile(tmp_path).collect()
    me = df.filter(pl.col("account_id") == 42)

    assert me.get_column("alive_s")[0] == 10
    assert me.get_column("slide_percent")[0] == pytest.approx(20.0)


def test_movement_profile_farm(movement_pq):
    df = queries.movement_profile(movement_pq).collect()
    me = df.filter(pl.col("account_id") == 42)

    assert me.get_column("farm_souls")[0] == 700
    assert me.get_column("farm_min")[0] == pytest.approx(700 / 30)
    assert me.get_column("souls_per_1000_units")[0] == pytest.approx(1000.0)


def test_movement_intervals_buckets(movement_pq):
    df = queries.movement_intervals(100, 42, 300, parquet_dir=movement_pq)

    assert len(df) == 6
    assert df.get_column("end_s").to_list() == [300, 600, 900, 1200, 1500, 1800]

    first = df.row(0, named=True)
    assert first["alive_s"] == 10
    assert first["slide_percent"] == pytest.approx(20.0)
    assert first["in_air_percent"] == pytest.approx(20.0)

    dead = df.row(3, named=True)
    assert dead["alive_s"] == 0
    assert dead["slide_percent"] is None
    assert dead["distance_min"] is None
    assert dead["distance"] == 0.0
    assert dead["dashes"] == 0


def test_movement_intervals_whole_match_matches_profile(movement_pq):
    df = queries.movement_intervals(100, 42, 1800, parquet_dir=movement_pq)
    me = queries.movement_profile(movement_pq).collect().filter(pl.col("account_id") == 42)
    row = df.row(0, named=True)

    assert len(df) == 1
    assert row["end_s"] == 1800
    assert row["distance"] == pytest.approx(me.get_column("distance")[0])
    assert row["stationary_percent"] == pytest.approx(me.get_column("stationary_percent")[0])
    assert row["distance_min"] == pytest.approx(me.get_column("distance_min")[0])
    assert row["combat_percent"] == pytest.approx(me.get_column("combat_percent")[0])


def test_movement_intervals_unknown_match(movement_pq):
    with pytest.raises(ValueError, match="match 999"):
        queries.movement_intervals(999, 42, parquet_dir=movement_pq)


def test_movement_intervals_account_without_rows(movement_pq):
    with pytest.raises(ValueError, match="no movement rows"):
        queries.movement_intervals(100, 99999, parquet_dir=movement_pq)


def test_movement_intervals_missing_table(tmp_path):
    infos = [build_movement_match()]
    for name, df in export.build_tables(infos, exclude=("movement", "movement_intervals")).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    with pytest.raises(ValueError, match="movement_intervals table not built"):
        queries.movement_intervals(100, 42, parquet_dir=tmp_path)


def test_movement_scoreboard_sums_lobby(movement_pq):
    df = queries.movement_scoreboard(100, parquet_dir=movement_pq).collect()
    me = df.filter(pl.col("account_id") == 42)

    assert set(df.get_column("account_id").to_list()) == {42, 43, 44}
    assert me.get_column("hero")[0] == "Mirage"
    assert me.get_column("alive_s")[0] == 10
    assert me.get_column("slide_percent")[0] == pytest.approx(20.0)


def test_movement_game_records_matches_profile(movement_pq):
    df = queries.movement_game_records(
        "Mirage", accounts=[42], parquet_dir=movement_pq, tz="America/Chicago"
    )
    me = queries.movement_profile(movement_pq).collect().filter(pl.col("account_id") == 42)

    assert len(df) == 1
    assert df.get_column("won").to_list() == [True]
    assert df.get_column("day").to_list() == [LOCAL_DAY]
    assert df.get_column("distance_min")[0] == pytest.approx(me.get_column("distance_min")[0])
    assert df.get_column("slide_percent")[0] == pytest.approx(20.0)
    assert df.get_column("combat_percent")[0] == pytest.approx(40.0)
    assert df.get_column("dashes_min")[0] == pytest.approx(6.0)


def test_movement_game_records_without_rows_keeps_nulls(tmp_path):
    infos = [build_movement_match(100), build_match(match_id=200)]

    for name, df in export.build_tables(infos).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.movement_game_records("Mirage", accounts=[42], parquet_dir=tmp_path)
    bare = df.filter(pl.col("match_id") == 200)

    assert len(df) == 2
    assert bare.get_column("distance_min")[0] is None
    assert bare.get_column("stationary_percent")[0] is None


def test_movement_game_records_unknown_hero(movement_pq):
    with pytest.raises(ValueError, match="Unknown hero"):
        queries.movement_game_records("Nobody", accounts=[42], parquet_dir=movement_pq)
