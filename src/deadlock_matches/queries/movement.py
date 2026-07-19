"""Movement metrics per interval, match, and game."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches.queries.core import _resolved_accounts, scan, table_exists
from deadlock_matches.queries.games import _collect_game_records, _hero_game_rows

if TYPE_CHECKING:
    from collections.abc import Sequence


MOVEMENT_COUNTS = [
    "alive_s",
    "moving_s",
    "stationary_s",
    "slide_s",
    "in_air_s",
    "zipline_s",
    "combat_s",
    "dashes",
    "air_dashes",
    "distance",
]


def _movement_percents() -> list[pl.Expr]:
    """Derive the percent and pace columns from summed movement counts."""
    alive = pl.col("alive_s")
    moving = pl.col("moving_s")

    return [
        pl.when(alive > 0).then(100 * pl.col("slide_s") / alive).alias("slide_percent"),
        pl.when(alive > 0).then(100 * pl.col("in_air_s") / alive).alias("in_air_percent"),
        pl.when(alive > 0).then(100 * pl.col("zipline_s") / alive).alias("zipline_percent"),
        pl.when(alive > 0).then(100 * pl.col("combat_s") / alive).alias("combat_percent"),
        pl.when(moving > 0).then(100 * pl.col("stationary_s") / moving).alias("stationary_percent"),
        pl.when(moving > 0).then(pl.col("distance") / (moving / 60)).alias("distance_min"),
    ]


def movement_intervals(
    match_id: int,
    account_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Split the movement for one player into intervals of distance and state counts.

    - sums the per minute movement_intervals rows into the requested buckets
    - percents cover alive seconds
    - stationary and pace cover moving seconds
    - intervals spent fully dead keep zero counts and null percents
    - the last interval ends at the match end, so it can be shorter than the rest
    """
    if not table_exists("movement_intervals", parquet_dir):
        msg = "movement_intervals table not built yet, run `deadlock sync`"
        raise ValueError(msg)

    duration = (
        scan("matches", parquet_dir).filter(pl.col("match_id") == match_id).select("duration_s")
    )
    buckets = (
        scan("movement_intervals", parquet_dir)
        .filter(pl.col("match_id") == match_id, pl.col("account_id") == account_id)
        .group_by((pl.col("start_s") // interval_s).alias("interval"))
        .agg(pl.col(MOVEMENT_COUNTS).sum())
    )
    duration, buckets = pl.collect_all([duration, buckets])

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    if buckets.is_empty():
        msg = f"account {account_id} has no movement rows in match {match_id}"
        raise ValueError(msg)

    duration_s = int(duration.item())
    last = buckets.select(pl.col("interval").max()).item()
    n = max((duration_s - 1) // interval_s + 1, last + 1)

    return (
        pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64})
        .join(buckets, on="interval", how="left")
        .sort("interval")
        .with_columns(pl.col(MOVEMENT_COUNTS).fill_null(0))
        .with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .with_columns(_movement_percents())
        .select(
            "start_s",
            "end_s",
            *MOVEMENT_COUNTS,
            "slide_percent",
            "in_air_percent",
            "zipline_percent",
            "combat_percent",
            "stationary_percent",
            "distance_min",
        )
    )


def movement_scoreboard(match_id: int, parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Sum the movement of every player in one match.

    - the movement_profile columns without the farm pace
    - hero and team come joined from the players table
    - players without movement rows stay out
    """
    return (
        scan("movement_intervals", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .group_by("match_id", "account_id")
        .agg(pl.col(MOVEMENT_COUNTS).sum())
        .with_columns(_movement_percents())
        .join(
            scan("players", parquet_dir).select("match_id", "account_id", "hero", "team"),
            on=["match_id", "account_id"],
        )
    )


def movement_metrics(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Sum the movement counts per player per match and derive the rates.

    - time sliding, in the air, ziplining, and fighting players as a percent
      of alive seconds
    - dashes and air dashes counted on the transition into the state
    - distance skips zipline seconds, respawn jumps, and other teleports
    """
    return (
        scan("movement_intervals", parquet_dir)
        .group_by("match_id", "account_id")
        .agg(pl.col(MOVEMENT_COUNTS).sum())
        .with_columns(_movement_percents())
        .with_columns(
            pl.when(pl.col("alive_s") > 0)
            .then(pl.col("dashes") / (pl.col("alive_s") / 60))
            .alias("dashes_min"),
            pl.when(pl.col("alive_s") > 0)
            .then(pl.col("air_dashes") / (pl.col("alive_s") / 60))
            .alias("air_dashes_min"),
        )
    )


def movement_profile(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Join the farm pace onto the movement metrics per player per match.

    - the movement_metrics columns
    - farm souls (troopers, jungle, treasure, denies) for pace per minute and per distance
    """
    grp = "match_id", "account_id"

    metrics = movement_metrics(parquet_dir)

    farm = (
        scan("soul_sources", parquet_dir)
        .filter(pl.col("source_name").is_in(["troopers", "jungle", "treasure", "denies"]))
        .group_by("match_id", "account_id", "source_name")
        .agg(pl.col("souls").max())
        .group_by(*grp)
        .agg(pl.col("souls").sum().alias("farm_souls"))
    )

    return (
        metrics.join(farm, on=list(grp), how="left")
        .join(scan("matches", parquet_dir).select("match_id", "duration_s"), on="match_id")
        .with_columns(
            pl.when(pl.col("duration_s") > 0)
            .then(pl.col("farm_souls") / (pl.col("duration_s") / 60))
            .alias("farm_min"),
            pl.when(pl.col("distance") > 0)
            .then(1000 * pl.col("farm_souls") / pl.col("distance"))
            .alias("souls_per_1000_units"),
        )
    )


def movement_game_records(
    hero: str,
    accounts: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
) -> pl.DataFrame:
    """Take one row per game of a hero with the movement metrics.

    - percents cover alive seconds
    - stationary and the pace cover moving seconds
    - distance skips zipline seconds, respawn jumps, and other teleports
    - dashes count the transition into the state
    - games without movement rows keep null metrics
    - days and since filter on the local day
    """
    accounts = _resolved_accounts(accounts)
    mine = _hero_game_rows(hero, accounts, parquet_dir, tz, days, since)
    metrics = movement_metrics(parquet_dir).select(
        "match_id",
        "account_id",
        "distance_min",
        "stationary_percent",
        "slide_percent",
        "in_air_percent",
        "zipline_percent",
        "combat_percent",
        "dashes_min",
        "air_dashes_min",
    )
    games = mine.join(metrics, on=["match_id", "account_id"], how="left")

    return _collect_game_records(games, hero, accounts)
