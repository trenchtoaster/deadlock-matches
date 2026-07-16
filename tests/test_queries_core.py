import datetime as dt

import polars as pl
import pytest
from builders import LOCAL_DAY, _write_item_history

from deadlock_matches import export, queries, schemas


def test_scan_reads_table(pq):
    assert queries.scan("matches", pq).collect().height == 1


def test_scan_unknown_table():
    with pytest.raises(ValueError, match="Unknown table"):
        queries.scan("test")


def test_table_exists(pq, movement_pq):
    assert queries.table_exists("deaths", pq)
    assert not queries.table_exists("movement", pq)
    assert queries.table_exists("movement", movement_pq)


def test_table_exists_unknown_table():
    with pytest.raises(ValueError, match="Unknown table"):
        queries.table_exists("test")


def test_my_games_filters_to_accounts(pq):
    df = queries.my_games(pq, accounts=[42], tz="America/Chicago").collect()

    assert df.height == 1
    assert df.get_column("account_id")[0] == 42
    assert df.get_column("won")[0] is True


def test_my_games_adds_local_day(pq):
    df = queries.my_games(pq, accounts=[42], tz="America/Chicago").collect()
    start_local = df.schema["start_local"]

    assert df.get_column("day")[0] == LOCAL_DAY
    assert isinstance(start_local, pl.Datetime)
    assert start_local.time_zone == "America/Chicago"


def test_my_games_requires_accounts(pq):
    with pytest.raises(ValueError, match="no accounts"):
        queries.my_games(pq, accounts=[])


def test_asset_tables_fall_back_to_the_main_store(tmp_path, monkeypatch):
    main = tmp_path / "main"
    other = tmp_path / "players"
    other.mkdir()
    _write_item_history(main)
    monkeypatch.setattr(export, "PARQUET_DIR", main)

    assert queries.table_exists("item_history", other)

    slots = queries.scan("item_history", other).collect()

    assert slots.get_column("class_name").to_list() == [
        "upgrade_crackshot",
        "upgrade_toxic_bullets",
    ]


def _write_upgrade_t_history(parquet_dir):
    rows = [
        {
            "item_id": 7,
            "name": "T",
            "class_name": "upgrade_t",
            "cost": cost,
            "slot": "weapon",
            "tier": 1,
            "is_active": False,
            "description": None,
            "era_from": dt.datetime(y, m, 1, tzinfo=dt.UTC),
            "client_version": build,
        }
        for cost, y, m, build in [(500, 2026, 1, 100), (800, 2026, 2, 200)]
    ]
    path = schemas.table_path("item_history", parquet_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    schemas.conform("item_history", rows).write_parquet(path)


def test_scan_routes_asset_tables_into_subfolder(tmp_path):
    _write_upgrade_t_history(tmp_path)

    assert queries.table_exists("item_history", tmp_path)
    assert not queries.table_exists("matches", tmp_path)
    assert queries.scan("item_history", tmp_path).select(pl.len()).collect().item() == 2


def test_asset_asof_picks_the_era_in_effect(tmp_path):
    _write_upgrade_t_history(tmp_path)
    left = pl.LazyFrame(
        {
            "item_id": [7, 7],
            "start_time": [
                dt.datetime(2026, 1, 15, tzinfo=dt.UTC),
                dt.datetime(2026, 3, 1, tzinfo=dt.UTC),
            ],
        }
    )

    out = queries.asset_asof(left, "item_history", by="item_id", parquet_dir=tmp_path)
    out = out.sort("start_time").collect()

    assert out.get_column("cost").to_list() == [500, 800]
    assert out.get_column("client_version").to_list() == [100, 200]


def test_asset_asof_older_than_all_eras_gets_earliest(tmp_path):
    _write_upgrade_t_history(tmp_path)
    left = pl.LazyFrame({"item_id": [7], "start_time": [dt.datetime(2025, 1, 1, tzinfo=dt.UTC)]})

    out = queries.asset_asof(left, "item_history", by="item_id", parquet_dir=tmp_path).collect()

    assert out.get_column("cost").to_list() == [500]
    assert out.get_column("client_version").to_list() == [100]


def test_skill_rating_labels_badge_columns():
    df = pl.DataFrame(
        {"average_badge_team0": [76, 83, 0, None]},
        schema={"average_badge_team0": pl.Int64},
    ).with_columns(queries.skill_rating("average_badge_team0").alias("label"))

    assert df.get_column("label").to_list() == ["Archon 6", "Oracle 3", "Obscurus", None]
