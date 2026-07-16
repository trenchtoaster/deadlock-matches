"""Shared table scans, account defaults, and era joins."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches import config, export, schemas
from deadlock_matches.assets import skill_rating as sr

if TYPE_CHECKING:
    from collections.abc import Sequence


_ERA_SENTINEL = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)


def scan(table: str, parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Lazily scan one exported table by name (one of schemas.TABLES).

    parquet_dir defaults to the standard export directory, here and in every
    query below. An asset table missing from parquet_dir is read from the
    standard export directory instead, so secondary stores like
    parquet-players share one copy.
    """
    if table not in schemas.TABLES:
        known = ", ".join(schemas.TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    parquet_dir = export.PARQUET_DIR if parquet_dir is None else parquet_dir

    if schemas.is_partitioned(table):
        directory = schemas.partition_dir(table, parquet_dir)

        if directory.is_dir():
            return pl.scan_parquet(str(directory / "*.parquet"))

    path = schemas.table_path(table, parquet_dir)

    if table in schemas.ASSET_TABLES and not path.exists():
        path = schemas.table_path(table, export.PARQUET_DIR)

    return pl.scan_parquet(path)


def table_exists(table: str, parquet_dir: str | Path | None = None) -> bool:
    """Whether a table is on disk, as a month-partitioned directory or a single parquet file.

    Asset tables fall back to the standard export directory like scan.
    """
    if table not in schemas.TABLES:
        known = ", ".join(schemas.TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    parquet_dir = export.PARQUET_DIR if parquet_dir is None else parquet_dir

    if schemas.is_partitioned(table):
        directory = schemas.partition_dir(table, parquet_dir)

        if directory.is_dir() and next(directory.glob("*.parquet"), None) is not None:
            return True

    if schemas.table_path(table, parquet_dir).exists():
        return True

    return table in schemas.ASSET_TABLES and schemas.table_path(table, export.PARQUET_DIR).exists()


def _asof_era_join(
    left: pl.LazyFrame,
    right: pl.LazyFrame,
    by: str | Sequence[str],
    on: str = "start_time",
) -> pl.LazyFrame:
    """Join right onto left by the era live at the time of each left row.

    - right carries an era_from datetime column and the join key(s) in by
    - backward as-of on era_from <= left[on], grouped by the key(s)
    - rows older than the first era fall back to the earliest era, matching record_asof
    """
    by_cols = [by] if isinstance(by, str) else list(by)
    prepared = right.with_columns(
        pl.when(pl.col("era_from") == pl.col("era_from").min().over(by_cols))
        .then(pl.lit(_ERA_SENTINEL))
        .otherwise(pl.col("era_from"))
        .alias("_join_from")
    ).sort("_join_from")

    return (
        left.sort(on)
        .join_asof(
            prepared,
            left_on=on,
            right_on="_join_from",
            by=by_cols,
            strategy="backward",
            check_sortedness=False,
        )
        .drop("_join_from")
    )


def asset_asof(
    left: pl.LazyFrame,
    table: str,
    by: str,
    on: str = "start_time",
    parquet_dir: str | Path | None = None,
) -> pl.LazyFrame:
    """Join a versioned asset table onto left rows by the era live at their time.

    - backward as-of on era_from <= left[on], grouped by the asset key
    - rows older than the first era fall back to the earliest era, matching record_asof
    """
    return _asof_era_join(left, scan(table, parquet_dir), by, on)


def my_games(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
) -> pl.LazyFrame:
    """Build one row per match the player appeared in, joined to match details.

    - adds start_local and day columns so grouping by day or week uses
      the local date, not the UTC date
    - accounts (Steam32 account IDs) and tz default to config.toml and
      the detected zone
    """
    accounts = config.config_accounts() if accounts is None else list(accounts)

    if not accounts:
        msg = "no accounts: pass accounts= or fill in accounts in config.toml"
        raise ValueError(msg)

    tz = config.config_timezone() if tz is None else tz

    return (
        scan("players", parquet_dir)
        .filter(pl.col("account_id").is_in(accounts))
        .join(scan("matches", parquet_dir), on="match_id")
        .with_columns(pl.col("start_time").dt.convert_time_zone(tz).alias("start_local"))
        .with_columns(pl.col("start_local").dt.date().alias("day"))
    )


def _local_day(frame: pl.LazyFrame, parquet_dir: str | Path | None, tz: str | None) -> pl.LazyFrame:
    """Join match start_time and add start_local/day columns in the given zone."""
    tz = config.config_timezone() if tz is None else tz

    return (
        frame.join(scan("matches", parquet_dir).select("match_id", "start_time"), on="match_id")
        .with_columns(pl.col("start_time").dt.convert_time_zone(tz).alias("start_local"))
        .with_columns(pl.col("start_local").dt.date().alias("day"))
    )


def _resolved_accounts(accounts: Sequence[int] | None) -> list[int]:
    """Resolve the accounts argument to config.toml when omitted."""
    resolved = config.config_accounts() if accounts is None else list(accounts)

    if not resolved:
        msg = "no accounts: pass accounts= or fill in accounts in config.toml"
        raise ValueError(msg)

    return resolved


def skill_rating(column: str) -> pl.Expr:
    """Skill rating labels for a badge level column.

    - the badge encoding and label text come from skill_rating.label
    """
    mapping = {
        tier * 10 + level: sr.label(tier * 10 + level)
        for tier in sr.tier_map()
        for level in range(7)
    }

    return pl.col(column).replace_strict(mapping, default=None, return_dtype=pl.String)
