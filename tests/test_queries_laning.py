import datetime as dt

import polars as pl
import pytest
from builders import LOCAL_DAY, build_lane_battle, build_laning_match

from deadlock_matches import export, queries


@pytest.fixture
def laning_pq(tmp_path):
    for name, df in export.build_tables([build_laning_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


def test_laning_stats_reads_the_last_snapshot_inside_the_window(laning_pq):
    df = queries.laning_stats(800, 540, parquet_dir=laning_pq)

    me = df.filter(pl.col("account_id") == 42).row(0, named=True)

    assert df.height == 4
    assert me["souls"] == 1800
    assert me["damage"] == 200
    assert me["obj_damage"] == 150
    assert me["snap_s"] == 180
    assert me["lane"] == "yellow"

    late = df.filter(pl.col("account_id") == 44).row(0, named=True)

    assert late["souls"] == 4000
    assert late["snap_s"] == 540
    assert late["lane"] == "green"


def test_laning_stats_counts_kills_inside_the_window(laning_pq):
    df = queries.laning_stats(800, 540, parquet_dir=laning_pq)

    kd = {r["account_id"]: (r["kills"], r["deaths"]) for r in df.iter_rows(named=True)}

    assert kd[42] == (1, 1)
    assert kd[43] == (1, 1)
    assert kd[44] == (0, 0)
    assert kd[45] == (0, 0)


def test_laning_stats_unknown_match(laning_pq):
    with pytest.raises(ValueError, match="not in the tables"):
        queries.laning_stats(999, 540, parquet_dir=laning_pq)


@pytest.fixture
def lane_pq(tmp_path):
    infos = [
        build_lane_battle(900, won=True),
        build_lane_battle(901, won=False, day=1, mate_deaths=(100, 200, 300, 800)),
        build_lane_battle(902, won=True, day=1, ally_abandon=400),
        build_lane_battle(903, won=True, day=1, not_scored=True),
    ]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


def test_lane_records_reads_the_last_snapshot_inside_the_mark(lane_pq):
    df = queries.lane_records(lane_pq, accounts=[42], tz="America/Chicago")

    first = df.filter(pl.col("match_id") == 900).row(0, named=True)

    assert df.get_column("match_id").to_list() == [900, 901, 902]
    assert first["lane"] == "yellow"
    assert first["lane_net"] == 1800
    assert first["won"]
    assert first["my_early"] == 1
    assert first["worst_early"] == 0
    assert not first["ally_left"]


def test_lane_records_counts_teammate_deaths_inside_the_window(lane_pq):
    df = queries.lane_records(lane_pq, accounts=[42], tz="America/Chicago")

    fed = df.filter(pl.col("match_id") == 901).row(0, named=True)

    assert fed["worst_early"] == 3
    assert fed["my_early"] == 1
    assert not fed["won"]


def test_lane_records_flags_the_ally_abandon(lane_pq):
    df = queries.lane_records(lane_pq, accounts=[42], tz="America/Chicago")

    assert df.filter(pl.col("ally_left")).get_column("match_id").to_list() == [902]


def test_lane_records_wider_mark_moves_the_snapshot_and_the_deaths(lane_pq):
    df = queries.lane_records(lane_pq, accounts=[42], tz="America/Chicago", mark_s=700)

    first = df.filter(pl.col("match_id") == 900).row(0, named=True)

    assert first["lane_net"] == 6000
    assert first["worst_early"] == 1


def test_lane_records_window_filters(lane_pq):
    days = queries.lane_records(lane_pq, accounts=[42], tz="America/Chicago", days=1)

    assert days.get_column("match_id").to_list() == [901, 902]

    later = queries.lane_records(
        lane_pq,
        accounts=[42],
        tz="America/Chicago",
        since=str(LOCAL_DAY + dt.timedelta(days=1)),
    )

    assert later.get_column("match_id").to_list() == [901, 902]

    hero = queries.lane_records(lane_pq, accounts=[42], tz="America/Chicago", hero="Haze")

    assert hero.is_empty()

    with pytest.raises(ValueError, match="Unknown hero"):
        queries.lane_records(lane_pq, accounts=[42], tz="America/Chicago", hero="Nobody")


def test_lane_records_drops_a_match_with_no_lane_snapshot(tmp_path):
    good = build_lane_battle(900, won=True)
    blank = build_lane_battle(901, won=True, day=1)
    blank.players[0].ClearField("stats")
    blank.players[1].ClearField("stats")

    for name, df in export.build_tables([good, blank], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.lane_records(tmp_path, accounts=[42], tz="America/Chicago")

    assert df.get_column("match_id").to_list() == [900]


def test_lane_records_drops_a_match_with_only_one_side_sampled(tmp_path):
    good = build_lane_battle(900, won=True)
    partial = build_lane_battle(901, won=True, day=1)
    partial.players[1].ClearField("stats")

    for name, df in export.build_tables([good, partial], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.lane_records(tmp_path, accounts=[42], tz="America/Chicago")

    assert df.get_column("match_id").to_list() == [900]
