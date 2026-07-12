import datetime as dt

import polars as pl
import pytest

from deadlock_matches import schemas
from deadlock_matches.assets import snapshots

MATCH_ROW = {
    "match_id": 1,
    "start_time": dt.datetime(2026, 7, 5, tzinfo=dt.UTC),
    "duration_s": 1800,
    "winning_team": 1,
    "match_mode": 1,
    "game_mode": 1,
    "average_badge_team0": 76,
    "average_badge_team1": 83,
    "not_scored": False,
}


def test_every_column_documented():
    for table, cols in schemas.TABLES.items():
        for name, col in cols.items():
            assert col.description, f"{table}.{name} has no description"


def test_conform_casts_to_the_table_schema():
    df = schemas.conform("matches", [MATCH_ROW])

    assert df.columns == list(schemas.TABLES["matches"])
    assert df.schema["start_time"] == pl.Datetime("us", "UTC")
    assert df.schema["match_id"] == pl.Int64


def test_conform_empty_rows_still_typed():
    df = schemas.conform("damage", [])

    assert df.height == 0
    assert df.schema["damage"] == pl.Int64
    assert df.columns == list(schemas.TABLES["damage"])


def test_conform_rejects_extra_column():
    with pytest.raises(ValueError, match="bogus"):
        schemas.conform("matches", [MATCH_ROW | {"bogus": 1}])


def test_conform_rejects_missing_column():
    row = dict(MATCH_ROW)
    row.pop("game_mode")

    with pytest.raises(ValueError, match="game_mode"):
        schemas.conform("matches", [row])


def test_stats_columns_use_souls_renames():
    cols = schemas.TABLES["stats"]

    assert "souls_player" in cols
    assert "gold_player" not in cols
    assert "time_stamp_s" in cols


def test_describe_single_table():
    out = schemas.describe("damage")

    for name in schemas.Damage.spec():
        assert name in out


def test_describe_all_tables():
    out = schemas.describe()

    for table in schemas.TABLES:
        assert table in out


def test_describe_unknown_table():
    with pytest.raises(ValueError, match="Unknown table"):
        schemas.describe("test")


def test_asset_tables_conform_empty_typed():
    for name in schemas.ASSET_TABLES:
        df = schemas.conform(name, [])

        assert df.height == 0
        assert df.columns == list(schemas.TABLES[name])


def test_weapon_history_columns_match_assets():
    cols = [
        c
        for c in schemas.TABLES["ability_weapon_history"]
        if c not in ("ability_class", "era_from", "client_version")
    ]

    assert tuple(cols) == snapshots.WEAPON_FIELDS
    assert schemas.WEAPON_HISTORY_FIELDS == snapshots.WEAPON_FIELDS


def test_table_path_routes_asset_tables(tmp_path):
    assert schemas.table_path("item_history", tmp_path) == tmp_path / "assets/item_history.parquet"
    assert schemas.table_path("matches", tmp_path) == tmp_path / "matches.parquet"


def test_partitioned_covers_match_tables_only(tmp_path):
    assert schemas.is_partitioned("matches")
    assert schemas.is_partitioned("movement")
    assert not schemas.is_partitioned("item_history")
    assert not schemas.is_partitioned("downloads")
    assert schemas.partition_dir("movement", tmp_path) == tmp_path / "movement"
