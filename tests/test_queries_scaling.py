import datetime as dt

import polars as pl
from builders import _hero_rec, _seed_hero_history

from deadlock_matches import queries


def test_hero_scaling_frame():
    df = queries.hero_scaling().collect()
    era = df.select("era_from").unique().sort("era_from")["era_from"][-1]
    mirage = df.filter((pl.col("hero_id") == 52) & (pl.col("era_from") == era)).sort("level")

    assert mirage.height == 36
    assert mirage.get_column("level").to_list() == list(range(1, 37))
    assert mirage.get_column("base_health")[0] < mirage.get_column("base_health")[-1]
    assert mirage.get_column("required_souls").is_sorted()
    assert df.get_column("client_version").null_count() == 0


def test_hero_scaling_asof_picks_era_correct_health(tmp_path, monkeypatch):
    _seed_hero_history(tmp_path, monkeypatch, _hero_rec(1000), _hero_rec(1200))
    left = pl.LazyFrame(
        {
            "hero_id": [52, 52],
            "level": [2, 2],
            "start_time": [
                dt.datetime(2026, 1, 15, tzinfo=dt.UTC),
                dt.datetime(2026, 2, 15, tzinfo=dt.UTC),
            ],
        }
    )

    out = queries.hero_scaling_asof(left).sort("start_time").collect()

    assert out.get_column("base_health").to_list() == [1010.0, 1210.0]


def test_hero_scaling_asof_coalesces_prehistory(tmp_path, monkeypatch):
    _seed_hero_history(tmp_path, monkeypatch, _hero_rec(1000), _hero_rec(1200))
    left = pl.LazyFrame(
        {
            "hero_id": [52],
            "level": [2],
            "start_time": [dt.datetime(2025, 6, 1, tzinfo=dt.UTC)],
        }
    )

    out = queries.hero_scaling_asof(left).collect()

    assert out.get_column("base_health").to_list() == [1010.0]
