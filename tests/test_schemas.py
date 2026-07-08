import datetime as dt

import polars as pl
import pytest

from deadlock_matches import schemas

MATCH_ROW = {
    "match_id": 1,
    "start_time": dt.datetime(2026, 7, 5, tzinfo=dt.UTC),
    "duration_s": 1800,
    "winning_team": 1,
    "match_mode": 1,
    "game_mode": 1,
    "average_badge_team0": 76,
    "average_badge_team1": 83,
}


def test_every_column_documented():
    for table, cols in schemas.TABLES.items():
        for name, col in cols.items():
            assert col.description, f"{table}.{name} has no description"


def test_conform_casts_and_orders():
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
